from google import genai
import os
import ast
import json
import re
import subprocess
from dotenv import load_dotenv
from agents.utils import staff_log, build_log

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)

_QC_MODEL = os.getenv("QC_MODEL", "gemini-2.5-flash")
MAX_FIX_ITERATIONS = 2


# ── 파일 타입별 정적 검사 ──────────────────────────────────────────────────────

def _check_python(file_path: str, code: str) -> list:
    """AST 파싱으로 Python 문법 오류 검사."""
    try:
        ast.parse(code)
        return []
    except SyntaxError as e:
        return [f"[{file_path}] SyntaxError line {e.lineno}: {e.msg}"]


def _check_js(file_path: str, full_path: str) -> list:
    """node --check 로 JS 문법 오류 검사. node가 없으면 건너뜀."""
    try:
        result = subprocess.run(
            ["node", "--check", full_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return [f"[{file_path}] JS Error: {result.stderr.strip()}"]
        return []
    except FileNotFoundError:
        return []  # node 미설치 환경은 건너뜀
    except subprocess.TimeoutExpired:
        return [f"[{file_path}] JS check timed out"]


def _check_html(file_path: str, code: str) -> list:
    """필수 HTML 구조 태그 존재 여부 검사."""
    errors = []
    lower = code.lower()
    for tag in ("<html", "<head", "<body"):
        if tag not in lower:
            errors.append(f"[{file_path}] HTML: '{tag}>' 태그 누락")
    return errors


def _run_syntax_checks(output_dir: str, codes: dict) -> list:
    """output 디렉토리의 실제 파일을 대상으로 모든 정적 검사 실행."""
    errors = []
    for file_path in codes:
        full_path = os.path.join(output_dir, file_path)
        if not os.path.exists(full_path):
            continue
        with open(full_path, encoding="utf-8") as f:
            code = f.read()

        if file_path.endswith(".py"):
            errors.extend(_check_python(file_path, code))
        elif file_path.endswith(".js"):
            errors.extend(_check_js(file_path, full_path))
        elif file_path.endswith(".html"):
            errors.extend(_check_html(file_path, code))
    return errors


# ── requirements.txt 유효성 검증 ─────────────────────────────────────────────

# PyPI 패키지명(소문자·언더스코어 정규화) → 코드 내 import 시 사용하는 최상위 모듈명
_PYPI_TO_IMPORT: dict = {
    "fastapi":                   "fastapi",
    "uvicorn":                   "uvicorn",
    "starlette":                 "starlette",
    "pydantic":                  "pydantic",
    "sqlalchemy":                "sqlalchemy",
    "alembic":                   "alembic",
    "websockets":                "websockets",
    "python_multipart":          "multipart",
    "aiofiles":                  "aiofiles",
    "httpx":                     "httpx",
    "requests":                  "requests",
    "python_dotenv":             "dotenv",
    "python_jose":               "jose",
    "passlib":                   "passlib",
    "pillow":                    "PIL",
    "bcrypt":                    "bcrypt",
    "cryptography":              "cryptography",
    "itsdangerous":              "itsdangerous",
    "jinja2":                    "jinja2",
    "aiosqlite":                 "aiosqlite",
    "asyncpg":                   "asyncpg",
    "psycopg2":                  "psycopg2",
    "psycopg2_binary":           "psycopg2",
    "pymysql":                   "pymysql",
    "motor":                     "motor",
    "pymongo":                   "pymongo",
    "redis":                     "redis",
    "celery":                    "celery",
    "boto3":                     "boto3",
    "openai":                    "openai",
    "anthropic":                 "anthropic",
    "google_genai":              "google",
    "google_generativeai":       "google",
    "numpy":                     "numpy",
    "pandas":                    "pandas",
    "scipy":                     "scipy",
    "matplotlib":                "matplotlib",
    "scikit_learn":              "sklearn",
    "torch":                     "torch",
    "tensorflow":                "tensorflow",
    "pytest":                    "pytest",
    "pytest_asyncio":            "pytest_asyncio",
    "httpx":                     "httpx",
    "anyio":                     "anyio",
    "email_validator":           "email_validator",
    "python_slugify":            "slugify",
    "pyyaml":                    "yaml",
    "toml":                      "toml",
    "click":                     "click",
    "rich":                      "rich",
    "loguru":                    "loguru",
}


def _normalize_pkg_name(raw: str) -> str:
    """PyPI 패키지명을 소문자 언더스코어 형식으로 정규화."""
    # extras 제거: uvicorn[standard] → uvicorn
    name = re.split(r'[\[>=<!;\s]', raw.strip())[0]
    return name.lower().replace("-", "_")


def _collect_imported_top_modules(codes: dict) -> set:
    """생성된 Python 파일에서 실제로 import된 최상위 모듈명 수집."""
    top_modules: set = set()
    for file_path, code in codes.items():
        if not file_path.endswith(".py"):
            continue
        for line in code.splitlines():
            line = line.strip()
            # `import X` / `import X.Y`
            m = re.match(r'^import\s+([\w.]+)', line)
            if m:
                top_modules.add(m.group(1).split(".")[0])
            # `from X import Y` / `from X.Y import Z`
            m2 = re.match(r'^from\s+([\w.]+)\s+import', line)
            if m2:
                top_modules.add(m2.group(1).split(".")[0])
    return top_modules


# import 없이도 실행에 필수인 인프라 패키지 (항상 유지)
_ALWAYS_KEEP_NORMALIZED: set = {
    "uvicorn",      # ASGI 서버 (CLI로 실행, 코드에 import 안 함)
    "gunicorn",     # WSGI/ASGI 서버 (CLI)
    "hypercorn",    # ASGI 서버 (CLI)
    "daphne",       # ASGI 서버 (CLI)
}

# 명시적 import 대신 코드 내 특정 식별자 출현으로 필요 여부를 판단하는 패키지
# key: 정규화된 PyPI명, value: 코드 전체에서 검색할 정규식 패턴
_PYPI_TO_CODE_PATTERN: dict = {
    "websockets":       r'\bWebSocket\b',            # FastAPI WebSocket 기능이 내부적으로 사용
    "python_multipart": r'\b(Form|File|UploadFile)\b',  # FastAPI 파일·폼 업로드
}


def _fix_requirements_txt(output_dir: str, codes: dict) -> list:
    """requirements.txt에서 실제로 사용되지 않거나 존재하지 않는 패키지를 제거.

    전략:
      1. 생성된 Python 파일의 import 문에서 실제 사용 모듈명 수집
      2. _ALWAYS_KEEP_NORMALIZED 에 속하면 무조건 유지 (uvicorn 등 CLI 서버)
      3. _PYPI_TO_IMPORT 매핑표에 있으면 → 해당 import명이 코드에 있을 때만 유지
      4. 매핑표에 없으면 → pkg 이름 자체가 import에 보이면 유지, 그 외 제거
    """
    req_key = "requirements.txt"
    if req_key not in codes:
        return []

    imported = _collect_imported_top_modules(codes)

    # 코드 패턴 검색용: 모든 Python 파일 내용을 하나로 합침
    all_py_code = "\n".join(v for k, v in codes.items() if k.endswith(".py"))

    req_lines = codes[req_key].splitlines()
    new_lines: list = []
    removed: list = []

    for line in req_lines:
        stripped = line.strip()
        # 빈 줄·주석은 그대로 유지
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        pkg_norm = _normalize_pkg_name(stripped)

        # ① 항상 유지 목록 (서버 CLI 패키지)
        if pkg_norm in _ALWAYS_KEEP_NORMALIZED:
            new_lines.append(line)
            continue

        # ② 코드 패턴으로 필요 여부를 판단하는 패키지 (e.g. websockets, python-multipart)
        code_pattern = _PYPI_TO_CODE_PATTERN.get(pkg_norm)
        if code_pattern is not None:
            if re.search(code_pattern, all_py_code):
                new_lines.append(line)    # 패턴 발견 → 유지
            else:
                removed.append(stripped)  # 패턴 없음 → 제거
            continue

        # ③ 알려진 매핑표에서 import명 조회
        import_name = _PYPI_TO_IMPORT.get(pkg_norm)

        if import_name is not None:
            # 매핑표에 있는 패키지 → import 문에서 실제 사용 여부 확인
            if import_name in imported:
                new_lines.append(line)    # 사용됨 → 유지
            else:
                removed.append(stripped)  # 미사용 → 제거
        else:
            # ④ 매핑표 미등록 패키지 → pkg 이름 자체가 import에 보이면 유지
            pkg_base = pkg_norm.split("_")[0]  # e.g. psycopg2_binary → psycopg2
            if pkg_norm in imported or pkg_base in imported:
                new_lines.append(line)    # 유지
            else:
                removed.append(stripped)  # 알 수 없고 미사용 → 제거

    if not removed:
        return []

    new_content = "\n".join(new_lines)
    codes[req_key] = new_content
    full_path = os.path.join(output_dir, req_key)
    if os.path.exists(full_path):
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    return removed


# ── Python import 경로 사전 보정 ──────────────────────────────────────────────

def _fix_python_imports(output_dir: str, codes: dict) -> list:
    """모든 intra-project import를 절대경로로 변환하고 __init__.py를 자동 생성.

    처리 패턴:
      bare:     `from models import X`    → `from backend.models import X`
      relative: `from .models import X`   → `from backend.api.v1.endpoints.models import X` (해석 후 올바른 절대경로)
      wrong depth: `from ...models import X` → `from backend.models import X`
      pkg rel:  `from . import endpoints` → `from backend.api.v1 import endpoints`
    """
    fixed = []

    # 1. name → absolute dotted path 맵 구성 (모듈 + 패키지 모두)
    name_to_abs: dict = {}

    # 모든 디렉토리 경로 수집 (패키지 추적용)
    all_dirs: set = set()
    for file_path in codes:
        normalized = file_path.replace("\\", "/")
        if "/" in normalized:
            parts = normalized.split("/")
            for i in range(1, len(parts)):
                all_dirs.add("/".join(parts[:i]))

    # Python 파일이 실제로 존재하는 디렉토리만 수집
    # → JS/HTML 전용 프로젝트(src/, public/ 등)에 __init__.py가 생기는 문제 방지
    py_containing_dirs: set = set()
    for file_path in codes:
        if file_path.endswith(".py"):
            normalized = file_path.replace("\\", "/")
            parts = normalized.split("/")
            for i in range(1, len(parts)):
                py_containing_dirs.add("/".join(parts[:i]))

    # 패키지(디렉토리) 등록 — 먼저 추가해서 모듈이 같은 이름이면 모듈이 덮어씀
    for dir_path in sorted(all_dirs):
        pkg_name = dir_path.split("/")[-1]
        abs_dotted = dir_path.replace("/", ".")
        if pkg_name not in name_to_abs:
            name_to_abs[pkg_name] = abs_dotted

    # 모듈(.py 파일) 등록 — 같은 이름이면 모듈이 패키지를 덮어씀
    for file_path in codes:
        if not file_path.endswith(".py"):
            continue
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        if module_name == "__init__":
            continue
        abs_dotted = file_path.replace("\\", "/").replace("/", ".")[:-3]
        name_to_abs[module_name] = abs_dotted

    # 2. Python 파일이 있는 중간 디렉토리에만 __init__.py 자동 생성
    #    JS/HTML 전용 디렉토리(src/, public/ 등)는 건너뜀
    for dir_path in sorted(all_dirs):
        if dir_path not in py_containing_dirs:
            continue  # Python 파일 없는 디렉토리는 제외
        init_path = f"{dir_path}/__init__.py"
        full_init = os.path.join(output_dir, init_path)
        if not os.path.exists(full_init):
            os.makedirs(os.path.dirname(full_init), exist_ok=True)
            with open(full_init, "w", encoding="utf-8") as f:
                f.write("")
            if init_path not in codes:
                codes[init_path] = ""
            fixed.append(f"{init_path} (신규 생성)")

    # 3. 각 Python 파일의 import 구문 절대경로로 보정
    for file_path in list(codes.keys()):
        if not file_path.endswith(".py") or "/" not in file_path:
            continue

        code = codes[file_path]
        new_lines = []
        changed = False

        # 현재 파일 디렉토리의 절대 dotted path (상대 import 해석용)
        dir_abs = os.path.dirname(file_path).replace("\\", "/").replace("/", ".")
        dir_parts = dir_abs.split(".") if dir_abs else []

        for line in code.splitlines():

            # ── Case 1: 점(dot) 포함 상대 import ──────────────────────────────
            # 패턴 A: `from .X import Y`  (dots 바로 뒤에 모듈/패키지명)
            m_rel = re.match(r'^(\s*from\s+)(\.+)(\w+)(\s+import\s+.+)$', line)
            if m_rel:
                dots = m_rel.group(2)
                target_name = m_rel.group(3)
                import_tail = m_rel.group(4)
                dot_count = len(dots)
                levels_up = dot_count - 1

                if target_name in name_to_abs:
                    # 알려진 프로젝트 내 모듈/패키지 → 절대경로로 교체
                    new_line = f"from {name_to_abs[target_name]}{import_tail}"
                else:
                    # 미등록 이름 → dot 개수 기반으로 절대경로 계산만 수행
                    if levels_up == 0:
                        base_parts = dir_parts
                    elif levels_up < len(dir_parts):
                        base_parts = dir_parts[:-levels_up]
                    else:
                        base_parts = []
                    abs_target = ".".join(base_parts + [target_name]) if base_parts else target_name
                    new_line = f"from {abs_target}{import_tail}"

                new_lines.append(new_line)
                if new_line.strip() != line.strip():
                    changed = True
                continue

            # 패턴 B: `from . import X`  (dots 뒤에 모듈명 없이 바로 import)
            m_rel_pkg = re.match(r'^(\s*from\s+)(\.+)(\s+import\s+.+)$', line)
            if m_rel_pkg:
                dots = m_rel_pkg.group(2)
                import_tail = m_rel_pkg.group(3)
                dot_count = len(dots)
                levels_up = dot_count - 1

                if levels_up == 0:
                    base_pkg = dir_abs
                elif levels_up < len(dir_parts):
                    base_pkg = ".".join(dir_parts[:-levels_up])
                else:
                    base_pkg = ""

                if base_pkg:
                    new_line = f"from {base_pkg}{import_tail}"
                else:
                    new_line = line  # 해석 불가, 그대로 유지
                new_lines.append(new_line)
                if new_line.strip() != line.strip():
                    changed = True
                continue

            # ── Case 2: bare `from X import Y` → 절대경로 ─────────────────────
            m_bare = re.match(r'^(\s*from\s+)(\w+)(\s+import\s+.+)$', line)
            if m_bare and m_bare.group(2) in name_to_abs:
                target_name = m_bare.group(2)
                import_tail = m_bare.group(3)
                new_line = f"from {name_to_abs[target_name]}{import_tail}"
                new_lines.append(new_line)
                if new_line.strip() != line.strip():
                    changed = True
                continue

            # ── Case 3: bare `import X` → `from pkg import X` ─────────────────
            m_bare_imp = re.match(r'^(\s*import\s+)(\w+)(.*)$', line)
            if m_bare_imp and m_bare_imp.group(2) in name_to_abs:
                target_name = m_bare_imp.group(2)
                abs_path = name_to_abs[target_name]
                pkg_parts = abs_path.split(".")
                if len(pkg_parts) > 1:
                    pkg = ".".join(pkg_parts[:-1])
                    new_line = f"from {pkg} import {target_name}{m_bare_imp.group(3)}"
                else:
                    new_line = line  # 최상위 모듈은 그대로 유지
                new_lines.append(new_line)
                if new_line.strip() != line.strip():
                    changed = True
                continue

            new_lines.append(line)

        if changed:
            new_code = "\n".join(new_lines)
            codes[file_path] = new_code
            full_path = os.path.join(output_dir, file_path)
            if os.path.exists(full_path):
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(new_code)
            fixed.append(file_path)

    return fixed


# ── JS 누락 모듈 탐지 ────────────────────────────────────────────────────────

def _detect_missing_js_modules(codes: dict) -> list:
    """JS/TS 파일에서 로컬 import/require하는 모듈 중 파일 목록에 없는 것을 탐지.

    Returns:
        ["[파일경로] JS import 누락: '경로' (해석: 절대경로)", ...] 형태의 경고 목록
    """
    missing: list = []
    all_js_files = {p.replace("\\", "/") for p in codes if p.endswith((".js", ".ts", ".jsx", ".tsx"))}

    for file_path, code in codes.items():
        if not file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
            continue
        base_dir = os.path.dirname(file_path.replace("\\", "/"))

        patterns = [
            r'import\s+[^"\']*\s+from\s+[\'"](\.[^\'"\s]+)[\'"]',
            r'import\s*\([\'"](\.[^\'"\s]+)[\'"]\)',
            r'require\s*\(\s*[\'"](\.[^\'"\s]+)[\'"]\s*\)',
        ]
        seen = set()
        for pat in patterns:
            for m in re.finditer(pat, code):
                rel_path = m.group(1)
                # 절대 경로로 변환
                if base_dir:
                    abs_path = base_dir + "/" + rel_path
                else:
                    abs_path = rel_path
                abs_path = abs_path.replace("\\", "/")
                # ../ 같은 상위 경로 정규화
                parts = []
                for p in abs_path.split("/"):
                    if p == "..":
                        if parts:
                            parts.pop()
                    elif p and p != ".":
                        parts.append(p)
                abs_path = "/".join(parts)

                if abs_path in seen:
                    continue
                seen.add(abs_path)

                # 확장자가 없으면 .js / .ts / index.js 등 후보 시도
                candidates = [
                    abs_path,
                    abs_path + ".js",
                    abs_path + ".ts",
                    abs_path + "/index.js",
                    abs_path + "/index.ts",
                ]
                found = any(c in all_js_files for c in candidates)
                if not found:
                    msg = f"[{file_path}] JS import 누락: '{rel_path}' (해석: {abs_path})"
                    missing.append(msg)

    return missing


# ── Gemini 코드 리뷰 & 수정 ───────────────────────────────────────────────────

def _gemini_review_and_fix(
    prd: str,
    current_codes: dict,
    syntax_errors: list,
    project_domain: str = "APP",
) -> dict:
    """전체 코드베이스를 Gemini로 리뷰하고, 이슈와 수정 코드 반환.

    project_domain에 따라 도메인 특화 리뷰 항목을 추가합니다:
    - GAME: Canvas 루프 무결성, 물리 연산, pixel_sprites 렌더링
    - APP: DOM 조작 안정성, 이벤트 핸들러, API 연동
    """
    files_block = "\n".join(
        f"\n--- {path} ---\n{code}" for path, code in current_codes.items()
    )
    errors_block = (
        "\n=== 정적 검사에서 발견된 오류 ===\n" + "\n".join(syntax_errors)
        if syntax_errors else ""
    )

    # ── 도메인별 중점 검토 항목 ───────────────────────────────────────────────
    if project_domain == "GAME":
        domain_review_section = """
=== [GAME 도메인] 중점 검토 항목 ===
이 프로젝트는 게임입니다. 아래 항목을 최우선으로 검토하세요:

G1. Canvas 렌더링 무결성
    - requestAnimationFrame 루프가 올바르게 시작/종료되는지 확인
    - Canvas context(ctx) 취득이 null 체크 없이 사용되지 않는지 확인
    - clearRect()가 매 프레임마다 호출되는지 확인 (화면 잔상 방지)
    - drawSprite() 또는 픽셀 렌더링 함수가 실제로 호출되는지 확인

G2. 의존성 주입 무결성
    - 클래스 생성 시 필요한 의존성(map, config 등)이 생성자로 전달되는지 확인
    - window.player, window.map 같은 전역 변수 참조가 없는지 확인
    - new Player(map, config) 처럼 의존성 주입 패턴을 지키는지 확인

G3. 게임 루프 물리 연산
    - deltaTime(dt)이 update() 함수에 올바르게 전달되는지 확인
    - 충돌 감지 로직에서 isWalkable() 등 계약된 메서드를 올바르게 호출하는지 확인
    - 좌표 계산에서 NaN/Infinity 발생 가능성 확인

G4. Level-as-Code 준수
    - 맵/레벨 데이터가 fetch()로 외부 JSON을 읽지 않는지 확인
    - 맵 데이터는 반드시 JS 파일의 배열 상수로 정의되어야 함
    - fetch 실패로 검은 화면이 발생하는 패턴이 있으면 즉시 수정

G5. ESM 모듈 규칙 준수 (전역 변수 오염 방지)
    - window.xxx = ... 전역 변수 할당이 있으면 반드시 제거/수정
    - 최상위 스코프의 let/var/const 선언(export 없이)이 있으면 클래스/모듈로 이동
    - import/export 없는 <script> 내 비즈니스 로직이 HTML에 있으면 별도 .js 파일로 분리
    - require() / module.exports 방식이 있으면 ESM(import/export)으로 교체
"""
    else:
        domain_review_section = """
=== [APP 도메인] 중점 검토 항목 ===
이 프로젝트는 웹 앱입니다. 아래 항목을 최우선으로 검토하세요:

A1. DOM 조작 안정성
    - querySelector(), getElementById() 결과가 null일 때 안전하게 처리하는지 확인
    - DOMContentLoaded 이벤트 이후에 DOM 접근이 이루어지는지 확인
    - 동적으로 생성된 요소에 이벤트 리스너가 올바르게 연결되는지 확인

A2. 상태 관리 일관성
    - 전역 변수(window.xxx, 전역 let/var) 사용 대신 클래스나 모듈 스코프 관리인지 확인
    - 비동기 fetch 후 UI 업데이트가 적절히 이루어지는지 확인

A3. API 연동 안정성
    - fetch URL이 올바르게 구성되는지 (baseURL + endpoint)
    - 에러 응답(4xx, 5xx)이 처리되는지 확인
    - JSON 파싱 실패 시 예외 처리가 있는지 확인

A4. Lucide 아이콘 초기화
    - lucide.createIcons()가 DOM 로드 후 호출되는지 확인
    - data-lucide 속성이 올바른 아이콘 이름을 사용하는지 확인

A5. Anti-Smashing — Ghost File 탐지 (선언만 하고 로직은 HTML에 있는 패턴)
    - file_tree에 src/components/xxx.js 등 JS 파일이 선언되어 있는지 확인
    - 실제 코드에서 해당 파일을 import하지 않고, index.html의 <script>에 로직이 집중되어 있으면 수정
    - index.html 안에 50줄 이상의 비즈니스 로직 <script> 블록이 있으면 반드시 별도 파일로 분리
    - `<script type="module" src="src/index.js">` 외의 <script> 태그 내 로직은 모두 .js 파일로 이동

A6. 전역 변수 패턴 탐지 및 수정
    - JS 파일 내 window.xxx = ..., document.xxx = ... 패턴 전역 할당이 있으면 제거
    - 최상위 스코프 var/let/const (export 없이) 탐지 → 클래스 인스턴스 변수나 모듈 export로 리팩토링
    - 모듈 간 공유 상태가 필요한 경우, 최상위 App/Game 클래스에 모아서 DI로 주입
"""

    prompt = f"""
당신은 시니어 코드 리뷰어입니다.
아래 코드베이스를 검토하고 문제를 발견하면 수정해주세요.

프로젝트 도메인: {project_domain} ({"게임/Canvas 기반" if project_domain == "GAME" else "웹 앱/DOM 기반"})

=== 기획서 (PRD) ===
{prd}
{errors_block}
{domain_review_section}
=== 공통 검토 항목 ===
1. 문법 오류 및 런타임 에러 가능성
2. Python import 누락 또는 잘못된 경로
   - [중요] 반드시 절대경로 import 사용 (`from backend.models import X` 형식)
   - 상대경로 import (from .X, from ..X, from ...X) 는 절대 사용하지 마세요
   - bare import (from models import X) 도 사용하지 마세요
3. JS/TS import/require로 참조하지만 파일 목록에 없는 누락 파일
   - 예: `import Vector2 from './utils/vector2'` 인데 src/utils/vector2.js가 없는 경우
   - 이런 파일은 new_files에 완전한 코드를 생성해야 합니다
4. 클래스/함수 인터페이스 불일치 (한 파일에서 호출하는 메서드가 다른 파일에 없는 경우)
5. 프론트엔드-백엔드 API 연동 불일치 (URL, 메서드, 필드명)
6. 기획서 대비 핵심 기능 누락

=== 전체 코드베이스 ===
{files_block}

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "thought": "이 코드베이스의 핵심 문제와 QC 접근 전략 (1-2문장)",
    "issues": ["발견된 문제 설명 1", "발견된 문제 설명 2"],
    "fixed_files": {{
        "수정이_필요한_파일경로": "수정된_전체_코드"
    }},
    "new_files": {{
        "새로_생성할_파일경로": "파일_전체_코드"
    }},
    "summary": "전체 QC 결과 한 줄 요약"
}}

수정이 필요 없는 파일은 fixed_files에 포함하지 마세요.
코드에서 import/require하지만 파일 목록에 없는 파일은 new_files에 생성해 주세요.
수정할 문제가 전혀 없으면 issues를 빈 배열로, fixed_files와 new_files를 빈 객체로 반환하세요.
"""

    response = client.models.generate_content(
        model=_QC_MODEL,
        contents=prompt
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw.strip())
    return json.loads(raw)


# ── README 생성 ───────────────────────────────────────────────────────────────

def _generate_readme(state: dict, output_dir: str, codes: dict) -> None:
    """QC 완료 후 output 디렉토리에 실행법이 담긴 README.md 생성."""

    file_tree_block = "\n".join(f"- {path}: {desc}" for path, desc in state.get("file_tree", {}).items())
    files_block = "\n".join(f"\n--- {path} ---\n{code}" for path, code in codes.items())

    prompt = f"""
당신은 기술 문서 작성 전문가입니다.
아래 정보를 바탕으로 이 프로젝트를 처음 보는 개발자가 바로 실행할 수 있는 README.md를 작성해주세요.

=== 기획서 (PRD) ===
{state.get("prd", "")}

=== 파일 구조 ===
{file_tree_block}

=== 전체 코드 ===
{files_block}

README.md에 반드시 포함할 항목:
1. 프로젝트 제목 및 한 줄 설명
2. 기술 스택 (언어, 프레임워크, DB 등)
3. 디렉토리 구조 (트리 형태)
4. 사전 요구사항 (Python 버전, node 여부 등)
5. 설치 및 실행 방법
   - 백엔드: 가상환경 생성, 패키지 설치(requirements 명시), 서버 실행 명령어
   - 프론트엔드: 별도 빌드 불필요한 경우 브라우저 열기 방법, 또는 serve 명령어
6. 주요 API 엔드포인트 (있는 경우)
7. 실행 확인 방법 (접속 URL 등)

반드시 마크다운 형식으로만 답변하세요. JSON이나 다른 형식은 사용하지 마세요.
"""

    try:
        response = client.models.generate_content(
            model=_QC_MODEL,
            contents=prompt
        )
        readme_content = response.text.strip()
        # 혹시 ```markdown 블록으로 감싸진 경우 제거
        if readme_content.startswith("```"):
            readme_content = re.sub(r'^```(?:markdown)?\n?', '', readme_content)
            readme_content = re.sub(r'\n?```$', '', readme_content.strip())

        readme_path = os.path.join(output_dir, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        print(f"  📄 README.md 생성 완료 → {readme_path}")
    except Exception as e:
        print(f"  ⚠️  README.md 생성 실패: {e}")


# ── QC Agent 메인 ─────────────────────────────────────────────────────────────

def qc_agent(state: dict) -> dict:
    output_dir = os.path.join("output", state["project_name"])
    codes = dict(state.get("codes", {}))
    prd = state.get("prd", "")
    project_domain = state.get("project_domain", "APP")

    if not codes:
        state.update({"feedback": "검증할 코드가 없습니다.", "current_step": "ERROR"})
        return state

    # 0-a. requirements.txt 유효성 검증 (존재하지 않거나 미사용 패키지 제거)
    req_removed = _fix_requirements_txt(output_dir, codes)
    if req_removed:
        build_log(state, f"🗑️  requirements.txt 유령 패키지 제거 ({len(req_removed)}건): {', '.join(req_removed)}")

    # 0-b. Python import 경로 사전 보정 (상대/bare → 절대경로, 중간 __init__.py 생성)
    import_fixes = _fix_python_imports(output_dir, codes)
    if import_fixes:
        build_log(state, f"🔧 Import 경로 사전 보정 ({len(import_fixes)}건): {', '.join(import_fixes)}")

    all_issues = []
    total_fixed_files = set()

    for iteration in range(1, MAX_FIX_ITERATIONS + 1):
        build_log(state, f"🔍 QC 검증 {iteration}회차...")

        # 1. output 디렉토리의 실제 파일 내용 읽기
        current_codes = {}
        for file_path in codes:
            full_path = os.path.join(output_dir, file_path)
            if os.path.exists(full_path):
                with open(full_path, encoding="utf-8") as f:
                    current_codes[file_path] = f.read()

        # 2. 정적 문법 검사
        syntax_errors = _run_syntax_checks(output_dir, codes)

        # 2-b. JS/TS 누락 모듈 탐지 (import하는데 파일이 없는 경우)
        js_missing = _detect_missing_js_modules(codes)
        if js_missing:
            build_log(state, f"⚠️  누락 JS 모듈 {len(js_missing)}건 탐지")
            for msg in js_missing:
                print(f"      {msg}")
            syntax_errors.extend(js_missing)

        if syntax_errors:
            build_log(state, f"⚠️  문법/구조 오류 {len(syntax_errors)}건 발견")
            for err in [e for e in syntax_errors if not e.startswith("[") or "JS import 누락" not in e]:
                print(f"      {err}")
        else:
            build_log(state, "✅ 문법 검사 통과")

        # 3. Gemini 코드 리뷰 (도메인 인지형)
        try:
            result = _gemini_review_and_fix(prd, current_codes, syntax_errors, project_domain)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  ⚠️  Gemini 리뷰 파싱 실패: {e}")
            break

        if iteration == 1:
            thought = result.get("thought", "")
            if thought:
                staff_log(state, "QC", thought)

        issues = result.get("issues", [])
        fixed_files = result.get("fixed_files", {})
        summary = result.get("summary", "")

        if issues:
            all_issues.extend(issues)
            build_log(state, f"📋 이슈 {len(issues)}건: {', '.join(issues[:2])}{'...' if len(issues) > 2 else ''}")

        # 4. 수정 파일 적용
        new_files = result.get("new_files", {})
        if fixed_files or new_files:
            if fixed_files:
                build_log(state, f"🔧 {len(fixed_files)}개 파일 수정 적용 중...")
                for file_path, fixed_code in fixed_files.items():
                    full_path = os.path.join(output_dir, file_path)
                    parent = os.path.dirname(full_path)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(fixed_code)
                    codes[file_path] = fixed_code
                    total_fixed_files.add(file_path)

            if new_files:
                build_log(state, f"✨ {len(new_files)}개 누락 파일 신규 생성 중...")
                for file_path, new_code in new_files.items():
                    full_path = os.path.join(output_dir, file_path)
                    parent = os.path.dirname(full_path)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(new_code)
                    codes[file_path] = new_code
                    total_fixed_files.add(file_path)
                    build_log(state, f"    ✅ {file_path} 생성")

            build_log(state, "✅ 적용 완료")
        else:
            build_log(state, "✅ 추가 수정 필요 없음")
            # 이슈도 없고 수정/생성도 없으면 조기 종료
            if not issues and not syntax_errors and not new_files:
                build_log(state, "📝 README.md 생성 중...")
                _generate_readme(state, output_dir, codes)
                state.update({
                    "codes": codes,
                    "feedback": summary or "모든 파일 QC 통과",
                    "current_step": "DONE"
                })
                return state
            break  # 이슈는 있었지만 이미 직전 iteration에서 수정 완료

    # ── README 생성 & 최종 리포트 ─────────────────────────────────────────────
    build_log(state, "📝 README.md 생성 중...")
    _generate_readme(state, output_dir, codes)

    final_errors = _run_syntax_checks(output_dir, codes)

    report_lines = ["=== QC 최종 리포트 ==="]

    if all_issues:
        report_lines.append(f"\n발견된 이슈 ({len(all_issues)}건):")
        for i, issue in enumerate(all_issues, 1):
            report_lines.append(f"  {i}. {issue}")
    else:
        report_lines.append("\n이슈 없음")

    if total_fixed_files:
        report_lines.append(f"\n자동 수정된 파일 ({len(total_fixed_files)}개):")
        for f in sorted(total_fixed_files):
            report_lines.append(f"  - {f}")

    if final_errors:
        report_lines.append(f"\n⚠️  잔여 오류 ({len(final_errors)}건):")
        for err in final_errors:
            report_lines.append(f"  {err}")
    else:
        report_lines.append("\n✅ 최종 문법 검사 통과")

    state.update({
        "codes": codes,
        "feedback": "\n".join(report_lines),
        "current_step": "DONE"
    })
    return state
