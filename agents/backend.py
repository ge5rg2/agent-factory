from google import genai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)

_BE_MODEL = os.getenv("BE_MODEL", "gemini-2.5-flash")

_FRONTEND_EXTENSIONS = {".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}
_FRONTEND_DIR_PREFIXES = ("frontend", "static", "public", "src", "client", "web", "templates")

_BACKEND_EXTENSIONS = {".py", ".txt", ".cfg", ".ini", ".toml", ".yaml", ".yml"}


def _is_backend_file(file_path: str) -> bool:
    """파일이 백엔드 담당인지 판별."""
    normalized = file_path.replace("\\", "/").lower()
    ext = os.path.splitext(normalized)[1]

    if ext in _FRONTEND_EXTENSIONS:
        return False
    for prefix in _FRONTEND_DIR_PREFIXES:
        if normalized.startswith(prefix + "/"):
            return False

    if normalized == "design_spec.json":
        return False

    if ext in _BACKEND_EXTENSIONS:
        return True

    if not ext:
        return True

    return False


def backend_agent(state: dict) -> dict:
    """백엔드 파일을 생성하는 전문 에이전트.

    project_type이 frontend_only인 경우 즉시 반환합니다.
    interface_contracts를 활용해 파일 간 API 일관성을 보장합니다.
    """
    project_type = state.get("project_type", "fullstack")
    prd = state.get("prd", "")
    file_tree = state.get("file_tree", {})
    interface_contracts = state.get("interface_contracts", {})

    be_files = {path: desc for path, desc in file_tree.items() if _is_backend_file(path)}

    # 순수 프론트엔드 프로젝트는 백엔드 생성 불필요
    if project_type == "frontend_only":
        if be_files:
            print(f"  ⏭️  frontend_only 프로젝트 — BE 파일 생성 건너뜀 ({', '.join(be_files.keys())})")
        codes = state.get("codes", {})
        state.update({"codes": codes, "current_step": "QC"})
        return state

    if not be_files:
        state.update({"current_step": "QC"})
        return state

    codes = state.get("codes", {})
    all_files = "\n".join(f"- {path}: {desc}" for path, desc in file_tree.items())

    # 전체 인터페이스 계약 요약
    all_contracts_str = "\n".join(
        f"- {path}: {contract}" for path, contract in interface_contracts.items()
    ) if interface_contracts else "(인터페이스 계약 없음)"

    for file_path, file_description in be_files.items():
        print(f"  ⚙️  BE 생성 중: {file_path}")

        existing_codes_context = ""
        if codes:
            existing_codes_context = "\n\n=== 이미 생성된 파일들 ===\n"
            for existing_path, existing_code in codes.items():
                if existing_path != "design_spec.json":
                    existing_codes_context += f"\n--- {existing_path} ---\n{existing_code}\n"

        current_contract = interface_contracts.get(file_path, "")

        prompt = f"""
당신은 시니어 백엔드 개발자입니다.
아래 기획서와 파일 구조를 바탕으로 "{file_path}" 파일의 완전한 코드를 작성하세요.

=== 기획서 (PRD) ===
{prd}

=== 전체 파일 구조 ===
{all_files}
{existing_codes_context}

=== 인터페이스 계약 (반드시 준수) ===
이 파일이 반드시 구현해야 하는 API:
{current_contract or '(이 파일에 대한 계약 없음)'}

프로젝트 전체 인터페이스 계약:
{all_contracts_str}

=== 현재 작성할 파일 ===
파일 경로: {file_path}
파일 역할: {file_description}

요구사항:
1. 실제로 실행 가능한 완전한 코드를 작성하세요 (절대 생략 없이 전체 코드)
2. FastAPI 기반으로 구현하세요 (CORS 설정 포함)
3. [중요] 프로젝트 내 모듈 import 시 반드시 절대경로 import 사용
   - ✅ from backend.models import Customer
   - ❌ from .models import Customer (상대경로 금지)
4. [중요] 모든 Python 패키지 디렉토리에 빈 __init__.py 파일 생성
5. [매우 중요] requirements.txt는 실제로 import하는 PyPI 패키지만 포함
   표준 패키지 참고표:
   | PyPI 패키지명                    | import 사용명  |
   |----------------------------------|----------------|
   | fastapi>=0.100.0                 | fastapi        |
   | uvicorn[standard]>=0.20.0        | uvicorn        |
   | pydantic>=2.0.0                  | pydantic       |
   | sqlalchemy>=2.0.0                | sqlalchemy     |
   | python-dotenv>=1.0.0             | dotenv         |
   ❌ Python 표준 라이브러리(os, sys, math 등) 포함 금지
   ❌ 존재하지 않는 패키지(salt, ansible, sorten 등) 포함 금지
6. Pydantic v2 문법: model_config = ConfigDict(from_attributes=True)
7. SQLAlchemy 2.0 문법: from sqlalchemy.orm import DeclarativeBase

파일 확장자에 맞는 마크다운 코드 블록으로만 답변하세요. JSON 형식 사용 금지.
출력 형식 예시 (Python 파일인 경우):
```python
# 전체 코드
from fastapi import FastAPI
...
```

[필수] 코드 블록 앞뒤에 다른 텍스트나 설명을 추가하지 마세요.
[필수] 코드가 아무리 길어도 절대 생략하거나 잘라내지 마세요.
"""

        response = None
        try:
            response = client.models.generate_content(
                model=_BE_MODEL,
                contents=prompt,
            )
            raw = response.text.strip()

            # ── 1순위: 마크다운 코드 블록 추출 ──────────────────────────────
            code_match = re.search(r"```(?:[\w+\-]*)\n(.*?)```", raw, re.DOTALL)
            if code_match:
                codes[file_path] = code_match.group(1).rstrip()
                continue  # 성공 → 다음 파일로

            # ── 2순위: JSON {"code": ...} 파싱 (하위 호환) ──────────────────
            try:
                json_str = raw
                if raw.startswith("```"):
                    json_str = re.sub(r"^```(?:json)?\n?", "", raw)
                    json_str = re.sub(r"\n?```$", "", json_str.strip())
                result = json.loads(json_str)
                codes[file_path] = result.get("code", raw)
            except (json.JSONDecodeError, ValueError):
                # ── 3순위: 응답 전체를 코드로 사용 ─────────────────────────
                codes[file_path] = raw

        except Exception as e:
            print(f"  ⚠️  {file_path} 생성 실패: {e}")
            codes[file_path] = f"# 생성 실패: {e}"

    state.update({
        "codes": codes,
        "current_step": "QC",
    })
    return state
