from agents.pm import pm_agent
import json

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

    # PM 작업 시작
    print("\n" + "-" * 60)
    print("📋 [Phase 1/4] PM Agent - 기획 및 구조 설계 중...")
    print("-" * 60)

    state = pm_agent(state)

    # 결과 출력
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

    print("\n" + "=" * 60)
    print("✨ 다음 단계: Developer Agent 구현 예정")
    print("=" * 60)

if __name__ == "__main__":
    run_team()