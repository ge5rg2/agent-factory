import google.generativeai as genai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def pm_agent(state: dict):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')

    prompt = f"""
당신은 MVP 전문 기획자(PM)입니다.
사용자의 아이디어: {state['idea']}

위 아이디어를 구현하기 위한 최소 기능 제품(MVP)의 파일 구조를 정의해주세요.

필수 요구사항:
1. 기획서(PRD)에는 핵심 기능, 기술 스택, 주요 컴포넌트를 명확히 기술
2. file_tree는 실제 구현에 필요한 파일들을 프론트엔드/백엔드로 구분하여 작성
3. 각 파일의 역할을 구체적으로 설명

반드시 아래 JSON 형식으로만 답변하세요:
{{
    "prd": "기획 상세 내용 (핵심 기능, 기술 스택, 주요 컴포넌트 포함)",
    "file_tree": {{
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
        result = json.loads(response.text)

        # 상태 업데이트
        state.update({
            "prd": result.get("prd", ""),
            "file_tree": result.get("file_tree", {}),
            "codes": {},  # 코드는 아직 생성 전
            "feedback": "",
            "current_step": "FE_DEVELOP"
        })

        return state

    except json.JSONDecodeError as e:
        print(f"⚠️  JSON 파싱 오류: {e}")
        # Fallback: 텍스트에서 JSON 추출 시도
        if response:
            try:
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    state.update({
                        "prd": result.get("prd", ""),
                        "file_tree": result.get("file_tree", {}),
                        "codes": {},
                        "feedback": "",
                        "current_step": "FE_DEVELOP"
                    })
                    return state
            except (json.JSONDecodeError, AttributeError):
                pass

            # 최종 실패 시 원본 텍스트 반환
            state.update({
                "prd": response.text,
                "file_tree": {},
                "codes": {},
                "feedback": "JSON 파싱 실패",
                "current_step": "ERROR"
            })
        else:
            state.update({
                "prd": "",
                "file_tree": {},
                "codes": {},
                "feedback": "API 응답 없음",
                "current_step": "ERROR"
            })
        return state
    except Exception as e:
        print(f"⚠️  에러 발생: {e}")
        state.update({
            "prd": "",
            "file_tree": {},
            "codes": {},
            "feedback": f"에러: {str(e)}",
            "current_step": "ERROR"
        })
        return state