"""공유 유틸리티 — 에이전트 간 공통 헬퍼 함수."""

from datetime import datetime


def staff_log(state: dict, agent: str, message: str) -> None:
    """에이전트의 사고 과정을 staff_logs에 기록하고 콘솔에 출력.

    Args:
        state: AgentState dict (staff_logs 필드에 누적)
        agent: 에이전트 이름 (예: "PM", "DESIGNER", "FRONTEND")
        message: 사고 내용 메시지
    """
    entry = {
        "agent": agent,
        "message": message,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    state.setdefault("staff_logs", []).append(entry)
    print(f"  💭 [{agent}] {message}")
