# 🤖 MVP AI Factory (v1.2.0-Production)

**"No-Image, Contract-First, Domain-Aware"** - Gemini 기반의 범용 MVP 개발 엔진

본 프로젝트는 기획부터 배포 가능 코드까지, 외부 에셋 의존 없이 순수 코드로만 작동하는 완벽한 게임 및 웹 앱을 생성하는 자율 에이전트 팀입니다. 각 에이전트별로 최적화된 LLM을 할당하여 비용과 성능의 균형을 맞출 수 있습니다.

---

## 🏗️ 차세대 시스템 아키텍처 사양

### 1️⃣ 동적 모델 라우팅 (Dynamic Model Config)

- **Agent-Specific LLMs**: 기획(PM)이나 검증(QC)에는 추론력이 높은 Pro 모델을, 단순 구현(FE/BE)에는 빠르고 저렴한 Flash 모델을 환경변수(`.env`)로 개별 할당할 수 있습니다.

### 2️⃣ 지능형 도메인 판별 (Smart PM)

- **Domain Detection**: 프로젝트가 '실시간 렌더링(GAME)'인지 '기능 중심(APP)'인지 자동 판별합니다.
- **Backend-on-Demand**: 게임 도메인이더라도 **AI 연산, 서버 데이터 보존**이 필요하면 `fullstack`으로 구성하여 백엔드 로직을 포함합니다.
- **Level-as-Code**: 외부 JSON 맵 데이터를 로드하지 않고, `src/levels.js` 형태의 하드코딩된 상수 배열을 사용하여 비동기 로드 에러를 원천 차단합니다.

### 3️⃣ 데이터 기반 에셋 (No-Image Engine)

- **Pixel-as-Code**: `designer.py`는 외부 에셋 없이 `design_spec.json`에 직접 8비트/16비트 **픽셀 데이터 배열(Pixel Array)**을 정의합니다.
- **Unified Renderer**: `frontend.py`는 이 데이터를 읽어 캔버스에 직접 그리는 엔진을 내부적으로 구현합니다.

### 4️⃣ 계약 기반 코딩 및 QC (Contracts & Safe-Update)

- **Strict Dependency Injection**: 전역 변수를 금지하고, 생성자를 통해 인스턴스(Map, Player 등)를 주입받는 구조를 강제합니다.
- **Domain-Aware QC**: QC 에이전트는 프로젝트 도메인(GAME/APP)을 인지하여 도메인 특화 에러를 정밀 타겟팅합니다.
- **Delta Injection**: 2번 고도화 모드 시 기존 렌더링 방식을 보존하며 파괴적 수정 없이 기능만 추가합니다.

---

## 🚀 환경 설정 및 실행

### 1. 환경 변수 설정 (.env)

루트 디렉토리에 `.env` 파일을 생성하고 아래와 같이 에이전트별 모델을 설정합니다. (비용과 속도에 맞춰 커스텀 가능)

```env
# Google Gemini API Key
GEMINI_API_KEY=your_api_key_here

# Agent Specific Models (예시)
PM_MODEL=gemini-2.5-pro          # 기획 및 구조 설계 (높은 추론력 필요)
DESIGNER_MODEL=gemini-2.5-flash  # UI/UX 스펙 및 픽셀 아트 설계
FE_MODEL=gemini-2.5-flash-lite   # 프론트엔드 코드 대량 생성 (가성비/속도)
BE_MODEL=gemini-2.5-flash-lite   # 백엔드 코드 생성
QC_MODEL=gemini-2.5-pro          # 코드 검토 및 에러 수정 (정밀한 코드 리뷰)

```

### 2. 설치 및 실행

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 실행
python main.py

```

---

## 📂 프로젝트 구조 가이드

```text
agent-factory/
├── agents/
│   ├── pm.py          # 도메인 판별 및 인터페이스/맵 데이터 전략 수립
│   ├── designer.py    # 픽셀 아트 데이터 및 UI 스펙 생성
│   ├── frontend.py    # 데이터 기반 렌더링 및 UI 구현
│   ├── backend.py     # API 및 비즈니스 로직 구현
│   └── qc.py          # 도메인 인지형 정적 검사 및 자동 수정
├── .agent_logs/       # 체크포인트 및 작업 복구 폴더
├── state.py           # 공유 상태 스키마
├── main.py            # 신규-복구-고도화 제어 루프 메인 엔진
└── output/            # 실행 가능한 완성 프로젝트 보관함

```

---

## 📝 라이센스

MIT License
