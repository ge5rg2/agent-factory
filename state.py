from typing import TypedDict, Dict

class AgentState(TypedDict):
    idea: str              # 사용자의 최초 아이디어
    project_name: str      # 영어 프로젝트명 (output 디렉토리명)
    prd: str               # PM이 작성한 기획서
    file_tree: Dict[str, str] # 파일명과 파일 설명
    codes: Dict[str, str]  # 실제 생성된 파일별 코드 {파일명: 코드내용}
    feedback: str          # QC의 피드백
    current_step: str      # 현재 진행 단계