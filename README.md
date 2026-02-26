# 🤖 MVP AI Factory

**"아이디어를 MVP로"** - Gemini 기반 Multi-Agent 개발 시스템

ChatDev 아키텍처를 참고하여 Google Gemini에 최적화된 자동화 개발 파이프라인입니다.

---

## 📌 핵심 컨셉

사용자가 아이디어를 입력하면, **PM → Developer → QC → Deployer** 순서로 에이전트가 협업하여 실제 작동하는 MVP 코드를 생성합니다.

### 현재 구현 단계
- ✅ **Phase 1: PM Agent** - 기획서(PRD) 및 파일 구조 자동 생성
- 🔜 **Phase 2: Developer Agent** - 실제 코드 생성 (FE/BE)
- 🔜 **Phase 3: QC Agent** - 코드 리뷰 및 오류 검증
- 🔜 **Phase 4: Deployer** - 패키징 및 배포

---

## 🚀 빠른 시작

### 1. 사전 준비

**필수 요구사항:**
- Python 3.10 이상
- Google Gemini API Key ([발급받기](https://makersuite.google.com/app/apikey))

### 2. 설치

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
# .env 파일을 열어서 GOOGLE_API_KEY에 본인의 API 키를 입력하세요
```

### 3. 실행

```bash
python main.py
```

**예시 입력:**
```
💡 구현하고 싶은 아이디어를 입력하세요: 할일 관리 웹앱
```

**출력 결과:**
- 📋 PRD (기능 명세)
- 📁 File Tree (생성할 파일 구조)

---

## 📂 프로젝트 구조

```
agent-factory/
├── agents/
│   ├── pm.py          # PM Agent - 기획 및 구조 설계
│   ├── dev.py         # Developer Agent (예정)
│   └── qc.py          # QC Agent (예정)
├── state.py           # Agent 간 공유 상태 정의
├── main.py            # 메인 실행 파일
├── requirements.txt   # Python 의존성
├── .env.example       # 환경변수 템플릿
└── README.md
```

---

## 🎯 기술 스택

| 구분 | 기술 |
|------|------|
| **LLM** | Google Gemini 1.5 Pro/Flash |
| **프레임워크** | LangGraph (예정) |
| **언어** | Python 3.10+ |
| **컨텍스트 최적화** | Vertex AI Context Caching |

---

## 💡 ChatDev 대비 차별점

1. **토큰 최적화**: 파일 단위 컨텍스트 관리로 비용 절감
2. **Human-in-the-loop**: PM 단계 후 사용자 승인 단계 포함 (예정)
3. **Gemini 특화**: JSON Mode 및 Context Caching 활용

---

## 🛠️ 다음 단계

- [ ] Developer Agent 구현 (코드 자동 생성)
- [ ] QC Agent 구현 (에러 검증 및 피드백 루프)
- [ ] LangGraph 통합 (순환 워크플로우)
- [ ] 실시간 미리보기 기능

---

## 📝 라이센스

MIT License

---

## 🤝 기여

이슈 및 PR 환영합니다!
