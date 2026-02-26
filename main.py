from agents.pm import pm_agent
from agents.dev import dev_agent
from agents.qc import qc_agent
import os

def run_team():
    print("=" * 60)
    print("🤖 MVP AI Factory - Idea to MVP Pipeline")
    print("=" * 60)

    user_idea = input("\n💡 구현하고 싶은 아이디어를 입력하세요: ")

    # 초기 상태 설정
    state = {
        "idea": user_idea,
        "project_name": "",
        "prd": "",
        "file_tree": {},
        "codes": {},
        "feedback": "",
        "current_step": "PLANNING"
    }

    # Phase 1: PM Agent
    print("\n" + "-" * 60)
    print("📋 [Phase 1/4] PM Agent - 기획 및 구조 설계 중...")
    print("-" * 60)

    state = pm_agent(state)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    print("\n✅ 기획 완료!\n")
    print("📄 PRD (Product Requirements Document):")
    print("-" * 60)
    print(state['prd'])

    print("\n\n📁 File Tree (생성될 파일 구조):")
    print("-" * 60)
    for file_path, description in state['file_tree'].items():
        print(f"  📄 {file_path}")
        print(f"      └─ {description}")

    # Phase 2: Developer Agent
    print("\n" + "-" * 60)
    print("💻 [Phase 2/4] Developer Agent - 코드 생성 중...")
    print("-" * 60)

    state = dev_agent(state)

    if state["current_step"] == "ERROR":
        print(f"\n❌ 오류 발생: {state['feedback']}")
        return

    print("\n✅ 코드 생성 완료!\n")
    print("📂 생성된 파일 목록:")
    print("-" * 60)
    for file_path in state['codes']:
        lines = len(state['codes'][file_path].splitlines())
        print(f"  ✅ {file_path} ({lines} lines)")

    # 생성된 코드를 output/<project_name>/ 디렉토리에 저장
    output_dir = os.path.join("output", state["project_name"])
    os.makedirs(output_dir, exist_ok=True)

    for file_path, code in state['codes'].items():
        full_path = os.path.join(output_dir, file_path)
        parent_dir = os.path.dirname(full_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(code)

    print(f"\n📁 코드가 '{output_dir}/' 디렉토리에 저장되었습니다.")

    # Phase 3: QC Agent
    print("\n" + "-" * 60)
    print("🔍 [Phase 3/4] QC Agent - 코드 검증 및 자동 수정 중...")
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

if __name__ == "__main__":
    run_team()