from typing import TypedDict, Dict, Any, Optional


class AgentState(TypedDict):
    idea: str                              # 사용자의 최초 아이디어
    project_name: str                      # 영어 프로젝트명 (output 디렉토리명)
    project_type: str                      # "frontend_only" | "fullstack" | "backend_only"
    prd: str                               # PM이 작성한 기획서
    file_tree: Dict[str, str]              # 파일명과 파일 설명
    interface_contracts: Dict[str, str]    # 파일별 공개 API 계약 (메서드 시그니처)
    design_spec: Dict[str, Any]            # Designer가 생성한 UI/UX 디자인 스펙
    codes: Dict[str, str]                  # 실제 생성된 파일별 코드 {파일명: 코드내용}
    feedback: str                          # QC의 피드백
    current_step: str                      # 현재 진행 단계
    mode: str                              # 실행 모드: "new" | "upgrade"
    log_path: Optional[str]               # 체크포인트 로그 파일 경로
