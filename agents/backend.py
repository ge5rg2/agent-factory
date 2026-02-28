from google import genai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)

_FRONTEND_EXTENSIONS = {".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}
_FRONTEND_DIR_PREFIXES = ("frontend", "static", "public", "src", "client", "web", "templates")

# 백엔드 에이전트가 처리하는 확장자
_BACKEND_EXTENSIONS = {".py", ".txt", ".cfg", ".ini", ".toml", ".yaml", ".yml"}


def _is_backend_file(file_path: str) -> bool:
    """파일이 백엔드 담당인지 판별."""
    normalized = file_path.replace("\\", "/").lower()
    ext = os.path.splitext(normalized)[1]

    # 프론트엔드 파일 제외
    if ext in _FRONTEND_EXTENSIONS:
        return False
    for prefix in _FRONTEND_DIR_PREFIXES:
        if normalized.startswith(prefix + "/"):
            return False

    # design_spec.json은 designer가 생성하므로 제외
    if normalized == "design_spec.json":
        return False

    if ext in _BACKEND_EXTENSIONS:
        return True

    # 확장자 없는 파일(Dockerfile, Makefile 등)도 백엔드 담당
    if not ext:
        return True

    return False


def backend_agent(state: dict) -> dict:
    """백엔드 파일을 생성하는 전문 에이전트.

    FastAPI 기반 비즈니스 로직과 API 엔드포인트를 구현합니다.
    Pydantic v2, SQLAlchemy 2.0 문법을 사용하고
    절대경로 import 및 올바른 requirements.txt를 생성합니다.
    """
    prd = state.get("prd", "")
    file_tree = state.get("file_tree", {})

    be_files = {path: desc for path, desc in file_tree.items() if _is_backend_file(path)}

    if not be_files:
        state.update({"current_step": "QC"})
        return state

    codes = state.get("codes", {})
    all_files = "\n".join(f"- {path}: {desc}" for path, desc in file_tree.items())

    for file_path, file_description in be_files.items():
        print(f"  ⚙️  BE 생성 중: {file_path}")

        existing_codes_context = ""
        if codes:
            existing_codes_context = "\n\n=== 이미 생성된 파일들 ===\n"
            for existing_path, existing_code in codes.items():
                if existing_path != "design_spec.json":
                    existing_codes_context += f"\n--- {existing_path} ---\n{existing_code}\n"

        prompt = f"""
당신은 시니어 백엔드 개발자입니다.
아래 기획서와 파일 구조를 바탕으로 "{file_path}" 파일의 완전한 코드를 작성하세요.

=== 기획서 (PRD) ===
{prd}

=== 전체 파일 구조 ===
{all_files}
{existing_codes_context}

=== 현재 작성할 파일 ===
파일 경로: {file_path}
파일 역할: {file_description}

요구사항:
1. 실제로 실행 가능한 완전한 코드를 작성하세요
2. 주석은 최소화하고 코드 자체가 명확하도록 작성하세요
3. FastAPI 기반으로 구현하세요 (CORS 설정 포함)
4. [중요] 프로젝트 내 모듈 import 시 반드시 절대경로 import 사용 (상대경로 import 절대 금지)
   - ✅ 올바른 예: `from backend.models import Customer`
   - ❌ 잘못된 예: `from models import Customer` (bare import)
   - ❌ 잘못된 예: `from .models import Customer` (상대경로)
   - 실행 컨텍스트: 프로젝트 루트에서 `uvicorn backend.main:app` 으로 실행
5. [중요] 모든 Python 패키지 디렉토리(하위 포함)에 빈 __init__.py 파일 생성
   - 예: backend/__init__.py, backend/api/__init__.py
6. [매우 중요] requirements.txt는 반드시 코드에서 실제로 import하는 PyPI 패키지만 포함
   표준 FastAPI 패키지 참고표:
   | PyPI 패키지명                    | import 사용명  |
   |----------------------------------|----------------|
   | fastapi>=0.100.0                 | fastapi        |
   | uvicorn[standard]>=0.20.0        | uvicorn        |
   | pydantic>=2.0.0                  | pydantic       |
   | sqlalchemy>=2.0.0                | sqlalchemy     |
   | alembic>=1.10.0                  | alembic        |
   | websockets>=10.0                 | websockets     |
   | python-multipart>=0.0.6          | multipart      |
   | aiofiles>=22.0.0                 | aiofiles       |
   | httpx>=0.23.0                    | httpx          |
   | requests>=2.28.0                 | requests       |
   | python-dotenv>=1.0.0             | dotenv         |
   | python-jose[cryptography]>=3.3.0 | jose           |
   | passlib[bcrypt]>=1.7.0           | passlib        |
   | pillow>=9.0.0                    | PIL            |
   ❌ 절대 포함 금지: salt, ansible, sorten, 존재 불명 패키지
   ❌ Python 표준 라이브러리(os, sys, math, json, asyncio, typing 등) 포함 금지
7. [중요] Pydantic v2 문법 사용
   - ✅ `model_config = ConfigDict(from_attributes=True)`
   - ❌ `class Config: orm_mode = True`
8. [중요] SQLAlchemy 2.0 문법 사용
   - ✅ `from sqlalchemy.orm import DeclarativeBase` + `class Base(DeclarativeBase): pass`
   - ❌ `from sqlalchemy.ext.declarative import declarative_base`

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "code": "파일의 전체 코드 내용"
}}
"""

        response = None
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw.strip())
            result = json.loads(raw)
            codes[file_path] = result.get("code", "")

        except json.JSONDecodeError:
            if response:
                try:
                    json_match = re.search(r"\{.*\}", response.text, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group())
                        codes[file_path] = result.get("code", "")
                    else:
                        code_match = re.search(r"```(?:\w+)?\n(.*?)```", response.text, re.DOTALL)
                        codes[file_path] = code_match.group(1) if code_match else response.text
                except (json.JSONDecodeError, AttributeError):
                    codes[file_path] = response.text if response else ""

        except Exception as e:
            print(f"  ⚠️  {file_path} 생성 실패: {e}")
            codes[file_path] = f"# 생성 실패: {e}"

    state.update({
        "codes": codes,
        "current_step": "QC",
    })
    return state
