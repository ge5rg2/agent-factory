from agents.pm import pm_agent, pm_upgrade_agent
from agents.designer import designer_agent
from agents.frontend import frontend_agent
from agents.backend import backend_agent
from agents.qc import qc_agent
import json
import os


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
                pass  # 바이너리 파일 건너뜀
    return codes


# ── 신규 빌드 ─────────────────────────────────────────────────────────────────

def run_new_build() -> None:
    """신규 MVP 빌드: PM → Designer → Frontend → Backend → QC"""
    user_idea = input("\n💡 구현하고 싶은 아이디어를 입력하세요: ")

    state = {
        "idea": user_idea,
        "project_name": "",
        "prd": "",
        "file_tree": {},
        "design_spec": {},
        "codes": {},
        "feedback": "",
        "current_step": "PLANNING",
        "mode": "new",
        "log_path": None,
    }

    # ── Phase 1: PM Agent ─────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("📋 [Phase 1/5] PM Agent - 기획 및 구조 설계 중...")
    print("-" * 60)

    state = pm_agent(state)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    print("\n✅ 기획 완료!\n")
    print("📄 PRD (Product Requirements Document):")
    print("-" * 60)
    print(state["prd"])

    print("\n\n📁 File Tree (생성될 파일 구조):")
    print("-" * 60)
    for file_path, description in state["file_tree"].items():
        print(f"  📄 {file_path}")
        print(f"      └─ {description}")

    # ── Phase 2: Designer Agent ───────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("🎨 [Phase 2/5] Designer Agent - UI/UX 디자인 스펙 설계 중...")
    print("-" * 60)

    state = designer_agent(state)

    design_spec = state.get("design_spec", {})
    theme = design_spec.get("theme", {})
    canvas_on = design_spec.get("canvas", {}).get("use_canvas", False)
    print(f"\n✅ 디자인 스펙 완료!")
    print(f"  🎨 Primary: {theme.get('primary', '-')} / BG: {theme.get('background', '-')}")
    print(f"  🖼️  Canvas: {'사용' if canvas_on else '미사용'}")
    strategy = design_spec.get("no_image_strategy", "")
    print(f"  🗺️  전략: {strategy[:60]}{'...' if len(strategy) > 60 else ''}")

    # ── Phase 3: Frontend Agent ───────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("💻 [Phase 3/5] Frontend Agent - 프론트엔드 코드 생성 중...")
    print("-" * 60)

    state = frontend_agent(state)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    fe_files = [p for p in state["codes"] if _is_frontend(p)]
    print(f"\n✅ FE 코드 생성 완료! ({len(fe_files)}개 파일)")

    # ── Phase 4: Backend Agent ────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("⚙️  [Phase 4/5] Backend Agent - 백엔드 코드 생성 중...")
    print("-" * 60)

    state = backend_agent(state)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    be_files = [p for p in state["codes"] if not _is_frontend(p)]
    print(f"\n✅ BE 코드 생성 완료! ({len(be_files)}개 파일)")

    # ── 전체 코드를 disk에 저장 ────────────────────────────────────────────────
    output_dir = os.path.join("output", state["project_name"])
    _save_codes_to_disk(output_dir, state["codes"])

    # 메타데이터 저장 (고도화 모드를 위해)
    _save_factory_meta(output_dir, {
        "idea": user_idea,
        "project_name": state["project_name"],
        "prd": state["prd"],
        "file_tree": state["file_tree"],
    })

    print(f"\n📁 코드가 '{output_dir}/' 디렉토리에 저장되었습니다.")
    print("\n📂 생성된 파일 목록:")
    print("-" * 60)
    for file_path, code in state["codes"].items():
        lines = len(code.splitlines())
        role = "🎨 FE" if _is_frontend(file_path) else "⚙️  BE"
        print(f"  {role}  {file_path} ({lines} lines)")

    # ── Phase 5: QC Agent ─────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("🔍 [Phase 5/5] QC Agent - 코드 검증 및 자동 수정 중...")
    print("-" * 60)

    state = qc_agent(state)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    print("\n" + state["feedback"])

    print("\n" + "=" * 60)
    print("🎉 MVP 생성 완료!")
    print(f"📂 결과물 위치: {output_dir}/")
    print("=" * 60)


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

    state = {
        "idea": meta.get("idea", ""),
        "project_name": project_name,
        "prd": meta.get("prd", ""),
        "file_tree": meta.get("file_tree", {}),
        "design_spec": {},
        "codes": existing_codes,
        "feedback": "",
        "current_step": "UPGRADE_PLANNING",
        "mode": "upgrade",
        "log_path": None,
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
            print("\n  ♻️  기존 design_spec.json 재사용 (디자인 일관성 유지)")
        except (json.JSONDecodeError, KeyError):
            state = designer_agent(state)
            print("\n  🎨 디자인 스펙 새로 생성")
    else:
        state = designer_agent(state)
        print("\n  🎨 디자인 스펙 새로 생성")

    # ── Phase 3 & 4: 델타 파일 FE/BE 생성 ────────────────────────────────────
    # file_tree를 delta_file_tree로 교체하여 에이전트가 델타 파일만 생성하도록 설정
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
    # state["codes"]에는 기존 코드 + 새로 생성된 델타 코드가 함께 있음
    _save_codes_to_disk(project_dir, state["codes"])

    # 메타데이터 업데이트 (file_tree에 델타 파일 병합)
    merged_file_tree = {**meta.get("file_tree", {}), **delta_file_tree}
    _save_factory_meta(project_dir, {
        "idea": meta.get("idea", ""),
        "project_name": project_name,
        "prd": state["prd"],
        "file_tree": merged_file_tree,
    })

    # QC용으로 전체 file_tree 복원
    state["file_tree"] = merged_file_tree

    print(f"\n📁 '{project_dir}/' 디렉토리 업데이트 완료.")
    print(f"\n📝 변경/추가된 파일:")
    for path in delta_file_tree:
        lines = len(state["codes"].get(path, "").splitlines())
        print(f"  ✅ {path} ({lines} lines)")

    # ── Phase 5: QC Agent ─────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("🔍 [Phase 5/5] QC Agent - 코드 검증 및 자동 수정 중...")
    print("-" * 60)

    state = qc_agent(state)

    print("\n" + state["feedback"])

    print("\n" + "=" * 60)
    print("🎉 프로젝트 고도화 완료!")
    print(f"📂 결과물 위치: {project_dir}/")
    print("=" * 60)


# ── 메인 엔트리포인트 ─────────────────────────────────────────────────────────

def run_team() -> None:
    print("=" * 60)
    print("🤖 MVP AI Factory - Idea to MVP Pipeline")
    print("=" * 60)
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
