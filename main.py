from agents.pm import pm_agent, pm_upgrade_agent
from agents.designer import designer_agent
from agents.frontend import frontend_agent
from agents.backend import backend_agent
from agents.qc import qc_agent
from agents.devops import devops_agent
from checkpoint import (
    save_checkpoint,
    list_active_checkpoints,
    archive_checkpoint,
    delete_checkpoint,
    PHASE_LABELS,
)
import json
import os
from datetime import datetime


_FRONTEND_EXTENSIONS = {".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}
_FRONTEND_DIR_PREFIXES = ("frontend", "static", "public", "src", "client", "web", "templates")


def _is_frontend(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    ext = os.path.splitext(normalized)[1]
    if ext in _FRONTEND_EXTENSIONS:
        return True
    for prefix in _FRONTEND_DIR_PREFIXES:
        if normalized.startswith(prefix + "/"):
            return True
    return False


# ── 파일 I/O 헬퍼 ──────────────────────────────────────────────────────────────

def _save_codes_to_disk(output_dir: str, codes: dict) -> None:
    """생성된 코드를 output 디렉토리에 저장."""
    os.makedirs(output_dir, exist_ok=True)
    for file_path, code in codes.items():
        full_path = os.path.join(output_dir, file_path)
        parent_dir = os.path.dirname(full_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(code)


def _append_history(state: dict, message: str) -> None:
    """타임스탬프와 함께 state['history']에 이벤트를 기록하고 로그 파일에도 씁니다."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {message}"
    history = state.setdefault("history", [])
    history.append(line)

    # 로그 파일에도 기록 (output/{project_name}/.build_log.txt)
    project_name = state.get("project_name", "")
    if project_name:
        log_dir = os.path.join("output", project_name)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, ".build_log.txt")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _save_factory_meta(project_dir: str, meta: dict) -> None:
    """프로젝트 메타데이터를 .factory_meta.json에 저장."""
    meta_path = os.path.join(project_dir, ".factory_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_factory_meta(project_dir: str) -> dict:
    """프로젝트 메타데이터 로드. 없으면 빈 dict 반환."""
    meta_path = os.path.join(project_dir, ".factory_meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _read_project_codes(project_dir: str) -> dict:
    """프로젝트 디렉토리에서 모든 텍스트 파일을 읽어옴."""
    codes = {}
    skip_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules"}
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, project_dir).replace("\\", "/")
            try:
                with open(full_path, encoding="utf-8") as f:
                    codes[rel_path] = f.read()
            except UnicodeDecodeError:
                pass
    return codes


# ── 신규 빌드 공통 후반부 (Phase 2~6) ─────────────────────────────────────────

def _run_phases_2_to_6(state: dict, log_path: str, from_phase: str = "PM_DONE") -> None:
    """Designer → Frontend → Backend → (저장) → QC → DevOps 단계 실행.

    from_phase 인자로 중간 단계부터 재개할 수 있습니다.
    """
    output_dir = os.path.join("output", state["project_name"])
    skip_designer = from_phase not in ("PM_DONE",)
    skip_frontend = from_phase not in ("PM_DONE", "DESIGNER_DONE")
    skip_backend = from_phase not in ("PM_DONE", "DESIGNER_DONE", "FRONTEND_DONE")
    skip_save = from_phase in ("DISK_SAVED",)

    # ── Phase 2: Designer Agent ───────────────────────────────────────────────
    if not skip_designer:
        print("\n" + "-" * 60)
        print("🎨 [Phase 2/6] Designer Agent - UI/UX 디자인 스펙 설계 중...")
        print("-" * 60)
        _append_history(state, "Phase 2: Designer Agent 시작")

        state = designer_agent(state)

        design_spec = state.get("design_spec", {})
        theme = design_spec.get("theme", {})
        domain = design_spec.get("project_domain", state.get("project_domain", "APP"))
        has_sprites = "pixel_sprites" in design_spec
        has_ui_comps = "ui_components" in design_spec
        print(f"\n✅ 디자인 스펙 완료!")
        print(f"  🌐 Domain: {domain} ({'🎮 Canvas+Pixel' if domain == 'GAME' else '🖥️  DOM+Tailwind'})")
        print(f"  🎨 Primary: {theme.get('primary', '-')} / BG: {theme.get('background', '-')}")
        if domain == "GAME":
            sprite_count = len([k for k in design_spec.get("pixel_sprites", {}) if k not in ("color_palette", "sprite_scale")])
            print(f"  🕹️  Pixel Sprites: {sprite_count}개 {'✅' if has_sprites else '⚠️ 기본값'}")
        else:
            comp_count = len(design_spec.get("ui_components", {}))
            print(f"  🧩 UI Components: {comp_count}개 {'✅' if has_ui_comps else '⚠️ 기본값'}")

        _append_history(state, f"Phase 2 완료: domain={domain}, primary={theme.get('primary', '-')}")
        log_path = save_checkpoint(state, "DESIGNER_DONE")
    else:
        print("\n  ⏭️  [Phase 2] Designer 체크포인트 재사용 (건너뜀)")

    # ── Phase 3: Frontend Agent ───────────────────────────────────────────────
    if not skip_frontend:
        print("\n" + "-" * 60)
        print("💻 [Phase 3/6] Frontend Agent - 프론트엔드 코드 생성 중...")
        print("-" * 60)
        _append_history(state, "Phase 3: Frontend Agent 시작")

        state = frontend_agent(state)

        if state["current_step"] == "ERROR":
            print(f"\n❌ 오류 발생: {state['feedback']}")
            return

        fe_files = [p for p in state["codes"] if _is_frontend(p)]
        print(f"\n✅ FE 코드 생성 완료! ({len(fe_files)}개 파일)")
        _append_history(state, f"Phase 3 완료: FE 파일 {len(fe_files)}개 생성 — {', '.join(fe_files[:5])}")

        log_path = save_checkpoint(state, "FRONTEND_DONE")
    else:
        print("\n  ⏭️  [Phase 3] Frontend 체크포인트 재사용 (건너뜀)")

    # ── Phase 4: Backend Agent ────────────────────────────────────────────────
    if not skip_backend:
        print("\n" + "-" * 60)
        print("⚙️  [Phase 4/6] Backend Agent - 백엔드 코드 생성 중...")
        print("-" * 60)
        _append_history(state, "Phase 4: Backend Agent 시작")

        state = backend_agent(state)

        if state["current_step"] == "ERROR":
            print(f"\n❌ 오류 발생: {state['feedback']}")
            return

        be_files = [p for p in state["codes"] if not _is_frontend(p)]
        print(f"\n✅ BE 코드 생성 완료! ({len(be_files)}개 파일)")
        _append_history(state, f"Phase 4 완료: BE 파일 {len(be_files)}개 생성")

        log_path = save_checkpoint(state, "BACKEND_DONE")
    else:
        print("\n  ⏭️  [Phase 4] Backend 체크포인트 재사용 (건너뜀)")

    # ── 전체 코드를 disk에 저장 ────────────────────────────────────────────────
    if not skip_save:
        _save_codes_to_disk(output_dir, state["codes"])
        _save_factory_meta(output_dir, {
            "idea": state.get("idea", ""),
            "project_name": state["project_name"],
            "project_type": state.get("project_type", ""),
            "project_domain": state.get("project_domain", "APP"),
            "prd": state["prd"],
            "file_tree": state["file_tree"],
            "interface_contracts": state.get("interface_contracts", {}),
            "deploy_url": state.get("deploy_url"),
        })
        log_path = save_checkpoint(state, "DISK_SAVED")

        print(f"\n📁 코드가 '{output_dir}/' 디렉토리에 저장되었습니다.")
        print("\n📂 생성된 파일 목록:")
        print("-" * 60)
        for file_path, code in state["codes"].items():
            lines = len(code.splitlines())
            role = "🎨 FE" if _is_frontend(file_path) else "⚙️  BE"
            print(f"  {role}  {file_path} ({lines} lines)")
        _append_history(state, f"디스크 저장 완료: {len(state['codes'])}개 파일 → {output_dir}/")
    else:
        # disk에서 codes 재로드 (QC 용)
        if not state.get("codes"):
            state["codes"] = _read_project_codes(output_dir)
        print(f"\n  ⏭️  코드 저장 체크포인트 재사용 ('{output_dir}/' 디렉토리)")

    # ── Phase 5: QC Agent ─────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("🔍 [Phase 5/6] QC Agent - 코드 검증 및 자동 수정 중...")
    print("-" * 60)
    _append_history(state, "Phase 5: QC Agent 시작")

    state = qc_agent(state)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    print("\n" + state["feedback"])
    _append_history(state, "Phase 5 완료: QC 검증 통과")

    # ── Phase 6: DevOps Agent ─────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("🚀 [Phase 6/6] DevOps Agent - 배포 중...")
    print("-" * 60)
    _append_history(state, "Phase 6: DevOps Agent 시작")

    state = devops_agent(state)

    deploy_url = state.get("deploy_url")
    if deploy_url:
        _append_history(state, f"Phase 6 완료: 배포 URL = {deploy_url}")
        # 배포 URL을 메타에 업데이트
        _save_factory_meta(output_dir, {
            "idea": state.get("idea", ""),
            "project_name": state["project_name"],
            "project_type": state.get("project_type", ""),
            "project_domain": state.get("project_domain", "APP"),
            "prd": state["prd"],
            "file_tree": state["file_tree"],
            "interface_contracts": state.get("interface_contracts", {}),
            "deploy_url": deploy_url,
        })
    else:
        _append_history(state, "Phase 6: 배포 건너뜀 (로컬 저장만)")

    # ── 빌드 로그 최종 저장 ────────────────────────────────────────────────────
    _flush_build_log(state, output_dir)

    # ── 정상 완료: 체크포인트 아카이브 ────────────────────────────────────────
    archive_checkpoint(log_path)

    print("\n" + "=" * 60)
    print("🎉 MVP 생성 완료!")
    print(f"📂 결과물 위치: {output_dir}/")
    if deploy_url:
        print(f"🌐 배포 URL: {deploy_url}")
    print("=" * 60)


def _flush_build_log(state: dict, output_dir: str) -> None:
    """전체 history를 output_dir/.build_log.txt에 최종 기록."""
    history = state.get("history", [])
    if not history:
        return
    os.makedirs(output_dir, exist_ok=True)
    log_file = os.path.join(output_dir, ".build_log.txt")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"# Build Log — {state.get('project_name', '')}\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n\n")
        for line in history:
            f.write(line + "\n")
    print(f"  📝 빌드 로그: {log_file}")


# ── 신규 빌드 ─────────────────────────────────────────────────────────────────

def run_new_build() -> None:
    """신규 MVP 빌드: PM → Designer → Frontend → Backend → QC"""
    user_idea = input("\n💡 구현하고 싶은 아이디어를 입력하세요: ")

    state = {
        "idea": user_idea,
        "project_name": "",
        "project_type": "",
        "project_domain": "",
        "prd": "",
        "file_tree": {},
        "interface_contracts": {},
        "design_spec": {},
        "codes": {},
        "feedback": "",
        "current_step": "PLANNING",
        "mode": "new",
        "log_path": None,
        "history": [],
        "deploy_url": None,
    }

    # ── Phase 1: PM Agent ─────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("📋 [Phase 1/5] PM Agent - 기획 및 구조 설계 중...")
    print("-" * 60)

    state = pm_agent(state)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    domain = state.get("project_domain", "APP")
    domain_icon = "🎮" if domain == "GAME" else "🖥️ "
    print(f"\n✅ 기획 완료! [{domain_icon} {domain} | {state.get('project_type', '')}]\n")
    print("📄 PRD (Product Requirements Document):")
    print("-" * 60)
    print(state["prd"])

    print("\n\n📁 File Tree (생성될 파일 구조):")
    print("-" * 60)
    for file_path, description in state["file_tree"].items():
        print(f"  📄 {file_path}")
        print(f"      └─ {description}")

    _append_history(state, f"Phase 1 완료: domain={domain}, type={state.get('project_type', '')}, 파일 {len(state['file_tree'])}개")

    # ── 체크포인트: PM 완료 ───────────────────────────────────────────────────
    log_path = save_checkpoint(state, "PM_DONE")
    print(f"\n  💾 체크포인트 저장: {log_path}")

    _run_phases_2_to_6(state, log_path, from_phase="PM_DONE")


# ── 체크포인트 복구 ───────────────────────────────────────────────────────────

def run_resume(checkpoint: dict) -> None:
    """중단된 파이프라인을 체크포인트에서 재가동."""
    state = checkpoint["state"]
    phase = checkpoint["phase_completed"]
    log_path = checkpoint["file_path"]

    project_name = state.get("project_name", "unknown")
    output_dir = os.path.join("output", project_name)

    print(f"\n  🔄 '{project_name}' 프로젝트 복구 시작")
    print(f"  📍 재개 지점: {PHASE_LABELS.get(phase, phase)}")

    if phase == "PM_DONE":
        _run_phases_2_to_6(state, log_path, from_phase="PM_DONE")

    elif phase == "DESIGNER_DONE":
        _run_phases_2_to_6(state, log_path, from_phase="DESIGNER_DONE")

    elif phase == "FRONTEND_DONE":
        _run_phases_2_to_6(state, log_path, from_phase="FRONTEND_DONE")

    elif phase in ("BACKEND_DONE",):
        _run_phases_2_to_6(state, log_path, from_phase="BACKEND_DONE")

    elif phase == "DISK_SAVED":
        # codes가 이미 disk에 있으므로 QC만 재실행
        if not state.get("codes"):
            state["codes"] = _read_project_codes(output_dir)

        print("\n" + "-" * 60)
        print("🔍 [Phase 5/5] QC Agent - 코드 검증 및 자동 수정 중...")
        print("-" * 60)

        state = qc_agent(state)
        print("\n" + state["feedback"])
        archive_checkpoint(log_path)

        print("\n" + "=" * 60)
        print("🎉 복구 완료!")
        print(f"📂 결과물 위치: {output_dir}/")
        print("=" * 60)

    else:
        print(f"\n⚠️  알 수 없는 체크포인트 단계: {phase}. 처음부터 다시 시작하세요.")
        delete_checkpoint(log_path)


# ── 기존 프로젝트 고도화 ──────────────────────────────────────────────────────

def run_upgrade() -> None:
    """기존 프로젝트 고도화 모드: 델타 파일만 재생성."""
    output_base = "output"

    if not os.path.isdir(output_base):
        print("\n⚠️  output/ 디렉토리가 없습니다. 먼저 신규 빌드를 실행하세요.")
        return

    projects = sorted(
        d for d in os.listdir(output_base)
        if os.path.isdir(os.path.join(output_base, d)) and not d.startswith(".")
    )

    if not projects:
        print("\n⚠️  고도화할 프로젝트가 없습니다. 먼저 신규 빌드를 실행하세요.")
        return

    print("\n📂 고도화할 프로젝트를 선택하세요:")
    for i, project in enumerate(projects, 1):
        project_dir = os.path.join(output_base, project)
        meta = _load_factory_meta(project_dir)
        idea_preview = meta.get("idea", "")[:40]
        print(f"  {i}. {project}" + (f"  ({idea_preview}...)" if idea_preview else ""))

    try:
        choice = int(input("\n번호 입력: ").strip()) - 1
        if not (0 <= choice < len(projects)):
            print("⚠️  올바른 번호를 입력하세요.")
            return
    except ValueError:
        print("⚠️  숫자를 입력하세요.")
        return

    project_name = projects[choice]
    project_dir = os.path.join(output_base, project_name)

    meta = _load_factory_meta(project_dir)
    existing_codes = _read_project_codes(project_dir)

    print(f"\n  ✅ '{project_name}' 프로젝트 로드 완료 ({len(existing_codes)}개 파일)")

    upgrade_request = input("\n✨ 어떤 기능을 추가하거나 수정할까요?\n   → ").strip()
    if not upgrade_request:
        print("⚠️  요청사항을 입력하세요.")
        return

    # 기존 배포 URL 복원 (Safe-Update: 동일 환경 재배포)
    existing_deploy_url = meta.get("deploy_url")
    if existing_deploy_url:
        print(f"\n  🌐 기존 배포 URL 감지: {existing_deploy_url}")
        print(f"  ♻️  업그레이드 후 동일 플랫폼에 재배포됩니다.")

    state = {
        "idea": meta.get("idea", ""),
        "project_name": project_name,
        "project_type": meta.get("project_type", ""),
        "project_domain": meta.get("project_domain", "APP"),
        "prd": meta.get("prd", ""),
        "file_tree": meta.get("file_tree", {}),
        "interface_contracts": meta.get("interface_contracts", {}),
        "design_spec": {},
        "codes": existing_codes,
        "feedback": "",
        "current_step": "UPGRADE_PLANNING",
        "mode": "upgrade",
        "log_path": None,
        "history": [],
        "deploy_url": existing_deploy_url,  # 기존 URL 보존 (재배포 시 업데이트)
    }

    # ── Phase 1: PM Upgrade Agent ─────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("📋 [Phase 1/5] PM Upgrade Agent - 변경 계획 수립 중...")
    print("-" * 60)

    state = pm_upgrade_agent(state, upgrade_request)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    delta_file_tree = state["file_tree"]
    change_summary = state["feedback"]

    if not delta_file_tree:
        print("\n⚠️  변경이 필요한 파일이 없습니다.")
        return

    print(f"\n✅ 변경 계획 완료!")
    print(f"  📝 {change_summary}")
    print(f"\n📁 델타 파일 ({len(delta_file_tree)}개):")
    for path, desc in delta_file_tree.items():
        icon = "✨ 신규" if path not in existing_codes else "📝 수정"
        print(f"  {icon}  {path}")
        print(f"        └─ {desc}")

    # ── Phase 2: Designer - 기존 design_spec 재사용 또는 새로 생성 ─────────────
    print("\n" + "-" * 60)
    print("🎨 [Phase 2/5] Designer - 디자인 스펙 확인 중...")
    print("-" * 60)

    if "design_spec.json" in existing_codes:
        try:
            existing_spec = json.loads(existing_codes["design_spec.json"])
            state["design_spec"] = existing_spec
            state["codes"]["design_spec.json"] = existing_codes["design_spec.json"]
            state["current_step"] = "FRONTEND_DEVELOP"
            # design_spec에 저장된 project_domain이 있으면 우선 사용
            if "project_domain" in existing_spec:
                state["project_domain"] = existing_spec["project_domain"]
            print("\n  ♻️  기존 design_spec.json 재사용 (디자인 일관성 유지)")
            domain = state.get("project_domain", "APP")
            print(f"  🌐 Domain: {domain} ({'🎮 Canvas+Pixel' if domain == 'GAME' else '🖥️  DOM+Tailwind'})")
        except (json.JSONDecodeError, KeyError):
            state = designer_agent(state)
            print("\n  🎨 디자인 스펙 새로 생성")
    else:
        state = designer_agent(state)
        print("\n  🎨 디자인 스펙 새로 생성")

    # ── Phase 3 & 4: 델타 파일 FE/BE 생성 ────────────────────────────────────
    fe_delta = {p: d for p, d in delta_file_tree.items() if _is_frontend(p)}
    be_delta = {p: d for p, d in delta_file_tree.items() if not _is_frontend(p)}

    if fe_delta:
        print("\n" + "-" * 60)
        print(f"💻 [Phase 3/5] Frontend Agent - {len(fe_delta)}개 FE 파일 업데이트 중...")
        print("-" * 60)
        state["file_tree"] = fe_delta
        state = frontend_agent(state)
    else:
        print("\n  ⏭️  FE 변경 없음 (Phase 3 건너뜀)")

    if be_delta:
        print("\n" + "-" * 60)
        print(f"⚙️  [Phase 4/5] Backend Agent - {len(be_delta)}개 BE 파일 업데이트 중...")
        print("-" * 60)
        state["file_tree"] = be_delta
        state = backend_agent(state)
    else:
        print("\n  ⏭️  BE 변경 없음 (Phase 4 건너뜀)")

    # ── 기존 코드 + 델타 코드 병합 & 저장 ────────────────────────────────────
    _save_codes_to_disk(project_dir, state["codes"])

    merged_file_tree = {**meta.get("file_tree", {}), **delta_file_tree}
    _save_factory_meta(project_dir, {
        "idea": meta.get("idea", ""),
        "project_name": project_name,
        "project_type": state.get("project_type", meta.get("project_type", "")),
        "project_domain": state.get("project_domain", meta.get("project_domain", "APP")),
        "prd": state["prd"],
        "file_tree": merged_file_tree,
        "interface_contracts": state.get("interface_contracts", meta.get("interface_contracts", {})),
        "deploy_url": state.get("deploy_url"),  # 기존 URL 보존
    })

    state["file_tree"] = merged_file_tree

    print(f"\n📁 '{project_dir}/' 디렉토리 업데이트 완료.")
    print(f"\n📝 변경/추가된 파일:")
    for path in delta_file_tree:
        lines = len(state["codes"].get(path, "").splitlines())
        print(f"  ✅ {path} ({lines} lines)")
    _append_history(state, f"업그레이드 저장 완료: 델타 {len(delta_file_tree)}개 파일")

    # ── Phase 5: QC Agent ─────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("🔍 [Phase 5/6] QC Agent - 코드 검증 및 자동 수정 중...")
    print("-" * 60)
    _append_history(state, "Phase 5: QC Agent 시작 (업그레이드)")

    state = qc_agent(state)

    print("\n" + state["feedback"])
    _append_history(state, "Phase 5 완료: QC 검증 통과")

    # ── Phase 6: DevOps 재배포 (Safe-Update) ─────────────────────────────────
    print("\n" + "-" * 60)
    print("🚀 [Phase 6/6] DevOps Agent - 업그레이드 재배포 중...")
    print("-" * 60)
    _append_history(state, "Phase 6: DevOps 재배포 시작 (Safe-Update)")

    state = devops_agent(state)

    new_deploy_url = state.get("deploy_url")
    if new_deploy_url:
        _append_history(state, f"Phase 6 완료: 재배포 URL = {new_deploy_url}")
        # 업데이트된 URL을 메타에 저장
        _save_factory_meta(project_dir, {
            "idea": meta.get("idea", ""),
            "project_name": project_name,
            "project_type": state.get("project_type", meta.get("project_type", "")),
            "project_domain": state.get("project_domain", meta.get("project_domain", "APP")),
            "prd": state["prd"],
            "file_tree": merged_file_tree,
            "interface_contracts": state.get("interface_contracts", meta.get("interface_contracts", {})),
            "deploy_url": new_deploy_url,
        })
    else:
        _append_history(state, "Phase 6: 배포 건너뜀 (로컬 저장만)")

    # 빌드 로그 최종 저장
    _flush_build_log(state, project_dir)

    print("\n" + "=" * 60)
    print("🎉 프로젝트 고도화 완료!")
    print(f"📂 결과물 위치: {project_dir}/")
    if new_deploy_url:
        print(f"🌐 배포 URL: {new_deploy_url}")
    print("=" * 60)


# ── 메인 엔트리포인트 ─────────────────────────────────────────────────────────

def _check_and_offer_resume() -> bool:
    """active 체크포인트가 있으면 사용자에게 복구 여부를 묻고 처리.

    Returns:
        True이면 복구를 진행했으므로 호출측에서 일반 메뉴를 건너뜁니다.
    """
    checkpoints = list_active_checkpoints()
    if not checkpoints:
        return False

    print("\n⚠️  이전에 중단된 작업이 감지되었습니다:")
    for i, cp in enumerate(checkpoints, 1):
        ts = cp["timestamp"][:19].replace("T", " ")
        label = PHASE_LABELS.get(cp["phase_completed"], cp["phase_completed"])
        print(f"  {i}. [{ts}] {cp['project_name']} — {label}")

    print()
    print("r. 중단된 작업 재개")
    print("d. 로그 삭제 후 새로 시작")
    print("s. 무시하고 계속 (새 메뉴로)")
    print()

    choice = input("선택 (r/d/s): ").strip().lower()

    if choice == "r":
        # 여러 개면 선택
        if len(checkpoints) == 1:
            run_resume(checkpoints[0])
        else:
            try:
                idx = int(input("재개할 번호: ").strip()) - 1
                if 0 <= idx < len(checkpoints):
                    run_resume(checkpoints[idx])
                else:
                    print("⚠️  올바른 번호를 입력하세요.")
            except ValueError:
                print("⚠️  숫자를 입력하세요.")
        return True

    elif choice == "d":
        for cp in checkpoints:
            delete_checkpoint(cp["file_path"])
        print("  🗑️  체크포인트 삭제 완료.")
        return False

    else:
        return False


def run_team() -> None:
    print("=" * 60)
    print("🤖 MVP AI Factory - Idea to MVP Pipeline")
    print("=" * 60)

    # ── 체크포인트 복구 확인 ──────────────────────────────────────────────────
    if _check_and_offer_resume():
        return

    print()
    print("1. 신규 빌드")
    print("2. 기존 프로젝트 고도화")
    print()

    choice = input("선택하세요 (1/2): ").strip()

    if choice == "1":
        run_new_build()
    elif choice == "2":
        run_upgrade()
    else:
        print("\n⚠️  올바른 번호를 입력하세요 (1 또는 2).")


if __name__ == "__main__":
    run_team()
