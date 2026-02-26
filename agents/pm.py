import google.generativeai as genai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def _flatten_file_tree(tree: dict, prefix: str = "") -> dict:
    """중첩된 dict 구조의 file_tree를 flat한 {파일경로: 설명} 형태로 변환."""
    result = {}
    for key, value in tree.items():
        path = f"{prefix}{key}" if not prefix else f"{prefix}/{key}"
        if isinstance(value, dict):
            result.update(_flatten_file_tree(value, path))
        elif isinstance(value, str):
            # 경로가 /로 끝나면 디렉토리이므로 건너뜀
            if not path.endswith("/"):
                result[path] = value
    return result

def pm_agent(state: dict):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')

    prompt = f"""
당신은 MVP 전문 기획자(PM)입니다.
사용자의 아이디어: {state['idea']}

위 아이디어를 구현하기 위한 최소 기능 제품(MVP)의 파일 구조를 정의해주세요.

필수 요구사항:
1. 기획서(PRD)는 한국어로 작성하되 문자열(string)로만 작성하세요
2. file_tree의 키는 반드시 실제 파일 경로(예: backend/main.py)여야 합니다. 디렉토리(backend/)나 중첩 dict는 절대 사용하지 마세요
3. 각 파일의 역할을 구체적으로 설명하세요
4. project_name은 영어 snake_case로 작성하세요 (예: todo_list_app)

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "project_name": "todo_list_app",
    "prd": "기획 상세 내용 (핵심 기능, 기술 스택, 주요 컴포넌트 포함) - 반드시 문자열로",
    "file_tree": {{
        "requirements.txt": "백엔드 Python 패키지 의존성 목록",
        "backend/__init__.py": "Python 패키지 초기화 파일 (빈 파일)",
        "backend/main.py": "FastAPI 메인 서버 - 라우팅 및 CORS 설정",
        "backend/models.py": "데이터 모델 정의",
        "frontend/index.html": "메인 페이지 UI",
        "frontend/app.js": "프론트엔드 로직"
    }}
}}
"""

    response = None
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # ```json ... ``` 마크다운 블록 제거
        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw.strip())

        result = json.loads(raw)

        file_tree = result.get("file_tree", {})
        # 중첩 dict가 올 경우 flat하게 변환
        if any(isinstance(v, dict) for v in file_tree.values()):
            file_tree = _flatten_file_tree(file_tree)
        # 디렉토리 경로(끝에 /) 제거
        file_tree = {k: v for k, v in file_tree.items() if not k.endswith("/")}

        prd = result.get("prd", "")
        if isinstance(prd, dict):
            prd = json.dumps(prd, ensure_ascii=False, indent=2)

        state.update({
            "project_name": result.get("project_name", "mvp_project"),
            "prd": prd,
            "file_tree": file_tree,
            "codes": {},
            "feedback": "",
            "current_step": "FE_DEVELOP"
        })
        return state

    except json.JSONDecodeError as e:
        print(f"⚠️  JSON 파싱 오류: {e}")
        if response:
            try:
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    file_tree = result.get("file_tree", {})
                    if any(isinstance(v, dict) for v in file_tree.values()):
                        file_tree = _flatten_file_tree(file_tree)
                    file_tree = {k: v for k, v in file_tree.items() if not k.endswith("/")}

                    prd = result.get("prd", "")
                    if isinstance(prd, dict):
                        prd = json.dumps(prd, ensure_ascii=False, indent=2)

                    state.update({
                        "project_name": result.get("project_name", "mvp_project"),
                        "prd": prd,
                        "file_tree": file_tree,
                        "codes": {},
                        "feedback": "",
                        "current_step": "FE_DEVELOP"
                    })
                    return state
            except (json.JSONDecodeError, AttributeError):
                pass

        state.update({
            "project_name": "mvp_project",
            "prd": response.text if response else "",
            "file_tree": {},
            "codes": {},
            "feedback": "JSON 파싱 실패",
            "current_step": "ERROR"
        })
        return state

    except Exception as e:
        print(f"⚠️  에러 발생: {e}")
        state.update({
            "project_name": "mvp_project",
            "prd": "",
            "file_tree": {},
            "codes": {},
            "feedback": f"에러: {str(e)}",
            "current_step": "ERROR"
        })
        return state
