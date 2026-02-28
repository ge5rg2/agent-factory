from agents.pm import pm_agent
from agents.designer import designer_agent
from agents.frontend import frontend_agent
from agents.backend import backend_agent
from agents.qc import qc_agent
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
    print(f"  🗺️  전략: {design_spec.get('no_image_strategy', '')[:60]}...")

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
        print("\n⚠️  고도화 모드는 준비 중입니다.")
    else:
        print("\n⚠️  올바른 번호를 입력하세요 (1 또는 2).")


if __name__ == "__main__":
    run_team()
