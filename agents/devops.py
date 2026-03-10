"""DevOps 에이전트 — 빌드된 프로젝트를 즉시 배포.

플랫폼 선택 전략 (자동 감지 + 수동 오버라이드):
  1. DEPLOY_PLATFORM 환경변수가 설정된 경우 → 해당 플랫폼 사용 (수동 오버라이드)
  2. DEPLOY_PLATFORM 미설정 시 PM이 결정한 project_type 기반 자동 선택:
       frontend_only          → vercel  (정적 파일 직접 배포에 최적)
       fullstack/backend_only → railway (컨테이너 풀스택 배포에 최적)

두 토큰을 모두 환경변수에 설정해두면 PM 판단에 따라 자동으로 적합한 플랫폼이 선택됩니다:
  VERCEL_TOKEN  — Vercel 배포 시 필요 (frontend_only 프로젝트)
  RAILWAY_TOKEN — Railway 배포 시 필요 (fullstack / backend_only 프로젝트)

배포 URL은 state['deploy_url']에 저장됩니다.
"""

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from agents.utils import staff_log

# requests 선택적 의존성 (Vercel API 사용 시 필요)
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_DEPLOY_PLATFORM = os.getenv("DEPLOY_PLATFORM", "").lower()
_VERCEL_TOKEN = os.getenv("VERCEL_TOKEN", "")
_RAILWAY_TOKEN = os.getenv("RAILWAY_TOKEN", "")

_SKIP_EXTS = {".pyc", ".pyo"}
_SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".factory_meta.json"}


# ── 로그 헬퍼 ─────────────────────────────────────────────────────────────────

def _log(state: dict, message: str) -> None:
    """콘솔 출력과 state['history'] 누적을 동시에 수행."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {message}"
    print(f"  {line}")
    history = state.setdefault("history", [])
    history.append(line)


# ── Vercel API 배포 ───────────────────────────────────────────────────────────

def _sha1_hex(content: bytes) -> str:
    return hashlib.sha1(content).hexdigest()


def _upload_file_vercel(token: str, content: bytes, sha: str) -> None:
    """단일 파일을 Vercel 파일 스토리지에 업로드."""
    resp = _requests.post(
        "https://api.vercel.com/v2/files",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "x-vercel-digest": sha,
            "Content-Length": str(len(content)),
        },
        data=content,
        timeout=30,
    )
    # 200: 업로드 성공, 409: 이미 존재 (SHA 중복, 정상)
    if resp.status_code not in (200, 409):
        resp.raise_for_status()


def _deploy_vercel(output_dir: str, project_name: str, token: str) -> str:
    """Vercel Deployments API v13으로 정적 파일을 GitHub 없이 직접 배포."""
    if not _HAS_REQUESTS:
        raise RuntimeError("Vercel 배포를 위해 'requests' 패키지가 필요합니다: pip install requests")

    # 1단계: 모든 파일 수집 + SHA 계산 + 업로드
    files_meta = []
    for root, dirs, fnames in os.walk(output_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in fnames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _SKIP_EXTS:
                continue
            full_path = os.path.join(root, fname)
            rel = os.path.relpath(full_path, output_dir).replace("\\", "/")
            # .factory_meta.json 등 메타 파일 제외
            if rel.startswith("."):
                continue
            with open(full_path, "rb") as f:
                content = f.read()
            sha = _sha1_hex(content)
            _upload_file_vercel(token, content, sha)
            files_meta.append({"file": rel, "sha": sha, "size": len(content)})

    # 2단계: 배포 생성
    safe_name = project_name.replace("_", "-").lower()
    payload = {
        "name": safe_name,
        "files": files_meta,
        "target": "production",
        "projectSettings": {"framework": None, "outputDirectory": None},
    }
    resp = _requests.post(
        "https://api.vercel.com/v13/deployments",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    # URL 추출 (alias > url)
    aliases = data.get("alias", [])
    raw_url = aliases[0] if aliases else data.get("url", "")
    return f"https://{raw_url}" if raw_url and not raw_url.startswith("http") else raw_url


# ── Railway CLI 배포 ──────────────────────────────────────────────────────────

def _deploy_railway(output_dir: str, project_name: str, token: str) -> str:
    """Railway CLI를 통해 풀스택 앱을 배포."""
    env = {**os.environ, "RAILWAY_TOKEN": token}

    # railway up: 현재 디렉토리를 서비스로 배포
    result = subprocess.run(
        ["railway", "up", "--detach", "--service", project_name],
        cwd=output_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Railway 배포 실패 (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    # 도메인 조회
    domain_result = subprocess.run(
        ["railway", "domain"],
        cwd=output_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    domain = domain_result.stdout.strip()
    return f"https://{domain}" if domain and not domain.startswith("http") else domain


# ── DevOps Agent 메인 ─────────────────────────────────────────────────────────

def devops_agent(state: dict) -> dict:
    """빌드 결과물을 project_type 기반으로 자동 선택된 플랫폼에 즉시 배포하는 에이전트.

    플랫폼 선택 우선순위:
      1. DEPLOY_PLATFORM 환경변수 (수동 오버라이드)
      2. project_type 자동 매핑: frontend_only → vercel, fullstack/backend_only → railway

    배포 성공 시: state['deploy_url'] 저장, state['current_step'] = 'DONE'
    배포 건너뜀:  state['deploy_url'] = None, state['current_step'] = 'DONE'
    배포 실패:    state['deploy_url'] = None, state['current_step'] = 'DONE' (경고만)
    """
    project_name = state.get("project_name", "")
    project_type = state.get("project_type", "fullstack")
    output_dir = os.path.join("output", project_name)

    # ── 플랫폼 결정: 수동 오버라이드 > project_type 자동 매핑 ─────────────────
    if _DEPLOY_PLATFORM:
        platform = _DEPLOY_PLATFORM                           # 수동 설정 우선
        _log(state, f"🔧 배포 플랫폼 수동 지정: {platform.upper()}")
    elif project_type == "frontend_only":
        platform = "vercel"                                   # 정적 파일 → Vercel
        _log(state, f"🤖 project_type=frontend_only → Vercel 자동 선택")
    elif project_type in ("fullstack", "backend_only"):
        platform = "railway"                                  # 풀스택/백엔드 → Railway
        _log(state, f"🤖 project_type={project_type} → Railway 자동 선택")
    else:
        platform = ""

    if not platform:
        staff_log(state, "DEVOPS", "배포 플랫폼을 결정할 수 없어 로컬 output/ 디렉토리에만 저장합니다. VERCEL_TOKEN 또는 RAILWAY_TOKEN을 설정하면 자동 배포가 활성화됩니다.")
        _log(state, "⏭️  배포 플랫폼 미결정 → 건너뜀 (로컬 output/ 디렉토리 사용)")
        state.update({"deploy_url": None, "current_step": "DONE"})
        return state

    staff_log(state, "DEVOPS", f"배포 환경을 구성하고 있습니다. PM이 결정한 {project_type} 프로젝트 → {platform.upper()} 플랫폼에 빌드 산출물을 업로드합니다.")
    _log(state, f"🚀 배포 시작: platform={platform.upper()}, project={project_name}")

    # ── Vercel 배포 (frontend_only 자동 선택) ────────────────────────────────
    if platform == "vercel":
        if not _VERCEL_TOKEN:
            staff_log(state, "DEVOPS", "VERCEL_TOKEN이 설정되지 않았습니다. .env 파일에 VERCEL_TOKEN을 추가해 주세요.")
            _log(state, "⚠️  VERCEL_TOKEN 미설정 → 배포 건너뜀")
            state.update({"deploy_url": None, "current_step": "DONE"})
            return state

        if project_type not in ("frontend_only",):
            _log(state, f"  ℹ️  project_type={project_type} — Vercel은 정적 파일만 배포합니다 (백엔드 코드 제외)")

        try:
            staff_log(state, "DEVOPS", "파일을 Vercel 서버에 업로드하는 중입니다. SHA1 중복 제거로 변경된 파일만 전송됩니다.")
            _log(state, f"  📤 파일 업로드 중: {output_dir}/")
            deploy_url = _deploy_vercel(output_dir, project_name, _VERCEL_TOKEN)
            staff_log(state, "DEVOPS", f"배포가 완료되었습니다! 서비스가 곧 접속 가능합니다: {deploy_url}")
            _log(state, f"  ✅ Vercel 배포 완료: {deploy_url}")
            state.update({"deploy_url": deploy_url, "current_step": "DONE"})

        except Exception as e:
            staff_log(state, "DEVOPS", "Vercel 배포 중 오류가 발생했습니다. 로컬 output/ 디렉토리에서 수동으로 배포해 주세요.")
            _log(state, f"  ❌ Vercel 배포 실패: {e}")
            state.update({"deploy_url": None, "current_step": "DONE"})

    # ── Railway 배포 (fullstack/backend_only 자동 선택) ──────────────────────
    elif platform == "railway":
        if not _RAILWAY_TOKEN:
            staff_log(state, "DEVOPS", "RAILWAY_TOKEN이 설정되지 않았습니다. .env 파일에 RAILWAY_TOKEN을 추가해 주세요.")
            _log(state, "⚠️  RAILWAY_TOKEN 미설정 → 배포 건너뜀")
            state.update({"deploy_url": None, "current_step": "DONE"})
            return state

        try:
            staff_log(state, "DEVOPS", "Railway 서비스를 시작하고 배포 파이프라인을 실행합니다. 빌드 완료 후 도메인이 자동 생성됩니다.")
            _log(state, f"  🚂 Railway 배포 중: {output_dir}/")
            deploy_url = _deploy_railway(output_dir, project_name, _RAILWAY_TOKEN)
            staff_log(state, "DEVOPS", f"배포가 완료되었습니다! 서비스가 곧 접속 가능합니다: {deploy_url}")
            _log(state, f"  ✅ Railway 배포 완료: {deploy_url}")
            state.update({"deploy_url": deploy_url, "current_step": "DONE"})

        except Exception as e:
            staff_log(state, "DEVOPS", "Railway 배포 중 오류가 발생했습니다. Railway CLI 설치 여부를 확인해 주세요.")
            _log(state, f"  ❌ Railway 배포 실패: {e}")
            _log(state, "  💡 Railway CLI가 설치되어 있는지 확인하세요: npm install -g @railway/cli")
            state.update({"deploy_url": None, "current_step": "DONE"})

    else:
        _log(state, f"⚠️  알 수 없는 배포 플랫폼: '{platform}' (vercel | railway 중 선택)")
        state.update({"deploy_url": None, "current_step": "DONE"})

    return state
