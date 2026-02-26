from google import genai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)

def dev_agent(state: dict):

    prd = state.get("prd", "")
    file_tree = state.get("file_tree", {})

    if not file_tree:
        state.update({
            "feedback": "file_tree가 비어 있어 코드를 생성할 수 없습니다.",
            "current_step": "ERROR"
        })
        return state

    codes = {}

    # 모든 파일 목록을 컨텍스트로 제공
    all_files = "\n".join(
        f"- {path}: {desc}" for path, desc in file_tree.items()
    )

    for file_path, file_description in file_tree.items():
        print(f"  ✍️  생성 중: {file_path}")

        # 이미 생성된 코드들을 컨텍스트로 제공 (파일 간 일관성 유지)
        existing_codes_context = ""
        if codes:
            existing_codes_context = "\n\n=== 이미 생성된 파일들 ===\n"
            for existing_path, existing_code in codes.items():
                existing_codes_context += f"\n--- {existing_path} ---\n{existing_code}\n"

        prompt = f"""
당신은 시니어 풀스택 개발자입니다.
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
3. 백엔드는 FastAPI, 프론트엔드는 순수 HTML/CSS/JS로 작성하세요
4. [중요] 프로젝트 내 모듈 import 시 반드시 절대경로 import 사용 (상대경로 import 절대 금지)
   - ✅ 올바른 예: `from backend.models import Customer`, `from backend.database import get_db`
   - ✅ 올바른 예: `from backend.api.v1.endpoints import customer`
   - ❌ 잘못된 예: `from models import Customer` (bare import)
   - ❌ 잘못된 예: `from .models import Customer` (상대경로)
   - ❌ 잘못된 예: `from ...models import Customer` (상대경로)
   - 실행 컨텍스트: 프로젝트 루트에서 `uvicorn backend.main:app` 으로 실행하므로 최상위 패키지명(예: backend)부터 시작하는 절대경로 사용
5. [중요] 모든 Python 패키지 디렉토리(하위 디렉토리 포함)에 빈 __init__.py 파일 생성
   - 예: backend/__init__.py, backend/api/__init__.py, backend/api/v1/__init__.py, backend/api/v1/endpoints/__init__.py
6. [중요] requirements.txt 작성 시 실제 사용하는 패키지와 버전 범위 명시
   - 예: `fastapi>=0.100.0`, `uvicorn>=0.20.0`, `sqlalchemy>=2.0.0`
7. [중요] Pydantic v2 문법 사용 (v1 문법 사용 금지)
   - ✅ `model_config = ConfigDict(from_attributes=True)`
   - ❌ `class Config: orm_mode = True`
8. [중요] SQLAlchemy 2.0 문법 사용
   - ✅ `from sqlalchemy.orm import DeclarativeBase` + `class Base(DeclarativeBase): pass`
   - ❌ `from sqlalchemy.ext.declarative import declarative_base` + `Base = declarative_base()`

반드시 아래 JSON 형식으로만 답변하세요:
{{
    "code": "파일의 전체 코드 내용"
}}
"""

        response = None
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt
            )
            result = json.loads(response.text)
            codes[file_path] = result.get("code", "")

        except json.JSONDecodeError:
            # Fallback: JSON 블록 추출 시도
            if response:
                try:
                    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group())
                        codes[file_path] = result.get("code", "")
                    else:
                        # 코드 블록에서 직접 추출
                        code_match = re.search(r'```(?:\w+)?\n(.*?)```', response.text, re.DOTALL)
                        codes[file_path] = code_match.group(1) if code_match else response.text
                except (json.JSONDecodeError, AttributeError):
                    codes[file_path] = response.text if response else ""

        except Exception as e:
            print(f"  ⚠️  {file_path} 생성 실패: {e}")
            codes[file_path] = f"# 생성 실패: {e}"

    state.update({
        "codes": codes,
        "current_step": "QC"
    })

    return state
