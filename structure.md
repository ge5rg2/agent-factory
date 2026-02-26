gemini-agent-factory/
├── agents/
│ ├── pm.py # 기획 및 구조 설계 에이전트
│ ├── dev.py # FE/BE 코드 작성 에이전트
│ └── qc.py # 코드 검토 에이전트
├── state.py # 에이전트들이 공유할 데이터 상태 정의
├── main.py # 전체 워크플로우 실행 파일 (LangGraph 설정)
└── .env # API 키 등 설정 파일
