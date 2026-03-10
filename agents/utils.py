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


def build_log(state: dict, message: str) -> None:
    """빌드 이벤트를 state['history']에 기록하고 콘솔에 출력.

    에이전트 내 print() 대체용 — 터미널 출력과 빌드 로그를 동기화합니다.

    Args:
        state: AgentState dict (history 필드에 누적)
        message: 이벤트 메시지
    """
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {message}"
    state.setdefault("history", []).append(line)
    print(line)
