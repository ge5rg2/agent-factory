from agents.pm import pm_agent
from agents.dev import dev_agent
import os

def run_team():
    print("=" * 60)
    print("🤖 MVP AI Factory - Idea to MVP Pipeline")
    print("=" * 60)

    user_idea = input("\n💡 구현하고 싶은 아이디어를 입력하세요: ")

    # 초기 상태 설정
    state = {
        "idea": user_idea,
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

    # 생성된 코드를 output/<아이디어명>/ 디렉토리에 저장
    idea_dirname = user_idea.strip().replace(" ", "_")
    output_dir = os.path.join("output", idea_dirname)
    os.makedirs(output_dir, exist_ok=True)

    for file_path, code in state['codes'].items():
        full_path = os.path.join(output_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(code)

    print(f"\n📁 코드가 '{output_dir}/' 디렉토리에 저장되었습니다.")

    print("\n" + "=" * 60)
    print("✨ 다음 단계: QC Agent 구현 예정")
    print("=" * 60)

if __name__ == "__main__":
    run_team()