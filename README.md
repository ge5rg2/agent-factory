# 🤖 MVP AI Factory (v1.0.0-Blueprint)

**"아이디어를 현실로"** - Gemini 2.5 Flash 기반의 자율 협업 멀티 에이전트 시스템입니다.
이 프로젝트는 기획, 디자인, 개발, 검증을 분업화하여 이미지 에셋 없이도 완성도 높은 MVP를 산출합니다.

---

## 🚀 빠른 시작

### 사전 준비

- Python 3.10 이상
- Google Gemini API Key ([발급받기](https://makersuite.google.com/app/apikey))

### 설치 및 실행

```bash
# 1. 저장소 클론 (또는 디렉토리 이동)
cd agent-factory

# 2. 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어서 GEMINI_API_KEY 또는 GOOGLE_API_KEY에 본인의 API 키 입력

# 5. 실행
python main.py
```

### 실행 모드

```
==============================
🤖 MVP AI Factory
==============================
1. 신규 빌드
2. 기존 프로젝트 고도화
선택하세요: _
```

---

## 📂 프로젝트 구조

```text
agent-factory/
├── agents/
│   ├── pm.py          # 기획 및 오케스트레이션 (Checkpoint 기록 담당)
│   ├── designer.py    # UI/UX 스펙 설계 (CSS·도형 중심, design_spec.json 생성)
│   ├── frontend.py    # FE 구현 전문 (Tailwind CSS, HTML5 Canvas)
│   ├── backend.py     # BE 구현 전문 (FastAPI, Pydantic v2, SQLAlchemy 2.0)
│   └── qc.py          # 정적 검사 및 자동 수정 루프
├── .agent_logs/       # 작업 로그 저장소
│   ├── active/        # 진행 중인 작업 상태
│   └── completed/     # 완료된 작업 아카이브
├── state.py           # design_spec, log_path 등 에이전트 공유 상태 정의
├── main.py            # 작업 모드 선택 및 복구 로직 컨트롤러
├── requirements.txt   # Python 의존성
├── .env.example       # 환경변수 템플릿
└── output/            # 생성된 MVP 프로젝트 보관함
```

---

## 🎯 5단계 파이프라인

```
PM Agent → Designer Agent → Frontend Agent → Backend Agent → QC Agent
 (기획)      (디자인 스펙)      (FE 코드)        (BE 코드)      (검증/수정)
```

| 단계 | 에이전트 | 산출물 |
|------|----------|--------|
| Phase 1 | `pm.py` | PRD, 파일 구조(file_tree), Checkpoint 기록 |
| Phase 2 | `designer.py` | `design_spec.json` (Tailwind 테마, 컬러, 도형 가이드) |
| Phase 3 | `frontend.py` | HTML/CSS/JS 파일 (Tailwind CDN, Canvas 선택적 사용) |
| Phase 4 | `backend.py` | FastAPI 서버, Pydantic 모델, SQLAlchemy ORM |
| Phase 5 | `qc.py` | 자동 수정, 최종 README.md 생성 |

---

## 🛠️ 기술 스택

| 구분 | 기술 |
|------|------|
| **Main LLM** | Google Gemini 2.5 Flash Preview |
| **SDK** | `google-genai>=1.0.0` |
| **Orchestration** | LangGraph (Stateful Workflow) |
| **Frontend** | Tailwind CSS CDN, HTML5 Canvas (No-image Design Strategy) |
| **Backend** | FastAPI, Pydantic v2, SQLAlchemy 2.0 |

---

## 💡 핵심 설계 원칙

### No-Image Design Strategy
이미지 에셋 없이 CSS 도형(`border-radius`, `gradient`, `box-shadow`)과 유니코드 문자만으로 완성도 높은 UI를 구현합니다.

### Ghost Package 방지
QC 에이전트가 `requirements.txt`에서 실제 코드에서 사용하지 않는 패키지를 자동 제거합니다.

### Fault Tolerance
작업 중단 시 `.agent_logs/active/`에 저장된 체크포인트에서 마지막 지점부터 파이프라인을 재가동합니다.

### Legacy Upgrade
기존 `output/` 내 프로젝트를 분석하여 변경이 필요한 파일의 '델타(Delta)'만 생성하는 고도화 모드를 지원합니다.

---

## 📝 라이센스

MIT License
