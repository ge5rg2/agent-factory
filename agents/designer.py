from google import genai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)


def _default_design_spec() -> dict:
    """파싱 실패 시 사용할 범용 기본 디자인 스펙."""
    return {
        "theme": {
            "primary": "blue-500",
            "secondary": "indigo-600",
            "background": "gray-50",
            "surface": "white",
            "text_primary": "gray-900",
            "text_secondary": "gray-600",
            "accent": "emerald-400",
            "danger": "red-500",
        },
        "typography": {
            "font_stack": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            "heading_weight": "font-bold",
            "body_size": "text-base",
        },
        "components": {
            "button_primary": "bg-blue-500 hover:bg-blue-600 text-white font-semibold py-2 px-4 rounded-lg transition-colors",
            "button_secondary": "bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold py-2 px-4 rounded-lg transition-colors",
            "card": "bg-white rounded-xl shadow-md p-6",
            "input": "w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500",
            "badge": "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800",
        },
        "layout": {
            "max_width": "max-w-7xl",
            "spacing": "space-y-4",
            "grid": "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        },
        "canvas": {
            "use_canvas": False,
            "canvas_guide": None,
        },
        "no_image_strategy": "CSS 도형(border-radius, gradient, box-shadow)과 유니코드 이모지를 활용한 이미지 대체",
    }


def designer_agent(state: dict) -> dict:
    """UI/UX 디자인 스펙(design_spec.json)을 생성하는 에이전트.

    Tailwind CSS 기반 테마, 컬러 팔레트, 도형 중심 디자인 가이드를 산출합니다.
    이미지 에셋 없이도 완성도 높은 UI를 구현하기 위한 No-Image Design Strategy를 정의합니다.
    """
    idea = state.get("idea", "")
    prd = state.get("prd", "")
    file_tree = state.get("file_tree", {})
    fe_files = [p for p in file_tree if _has_frontend_ext(p)]

    use_canvas_hint = "HTML5 Canvas" in prd or any(
        "game" in p.lower() or "canvas" in p.lower() for p in file_tree
    )

    prompt = f"""
당신은 시니어 UI/UX 디자이너입니다.
아래 기획서를 바탕으로 프로젝트의 디자인 시스템을 정의해주세요.

=== 아이디어 ===
{idea}

=== 기획서 (PRD) ===
{prd}

=== 프론트엔드 파일 목록 ===
{chr(10).join(f'- {p}' for p in fe_files) or '(없음)'}

디자인 원칙:
- Tailwind CSS CDN만 사용 (빌드 불필요)
- 이미지 파일 에셋 없이 CSS 도형(border-radius, gradient, box-shadow)과 유니코드 문자만으로 UI 구성
- HTML5 Canvas 사용 여부: {'게임이나 그래픽 집약적 기능이 있으면 true' if use_canvas_hint else '일반 UI는 false, 인터랙티브 그래픽 필요 시 true'}
- 프로젝트 특성에 맞는 감성적인 컬러 팔레트 선택

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "theme": {{
        "primary": "Tailwind 색상 클래스명 (예: blue-500)",
        "secondary": "Tailwind 색상 클래스명 (예: indigo-600)",
        "background": "Tailwind 색상 클래스명 (예: gray-50)",
        "surface": "Tailwind 색상 클래스명 (예: white)",
        "text_primary": "Tailwind 색상 클래스명 (예: gray-900)",
        "text_secondary": "Tailwind 색상 클래스명 (예: gray-600)",
        "accent": "Tailwind 색상 클래스명 (예: emerald-400)",
        "danger": "Tailwind 색상 클래스명 (예: red-500)"
    }},
    "typography": {{
        "font_stack": "CSS font-family 값 (예: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif)",
        "heading_weight": "font-bold 또는 font-extrabold",
        "body_size": "text-sm 또는 text-base"
    }},
    "components": {{
        "button_primary": "Tailwind 클래스 조합 문자열",
        "button_secondary": "Tailwind 클래스 조합 문자열",
        "card": "Tailwind 클래스 조합 문자열",
        "input": "Tailwind 클래스 조합 문자열",
        "badge": "Tailwind 클래스 조합 문자열"
    }},
    "layout": {{
        "max_width": "max-w-4xl 등 Tailwind 클래스",
        "spacing": "space-y-4 등 Tailwind 클래스",
        "grid": "grid grid-cols-1 md:grid-cols-2 등 Tailwind 클래스"
    }},
    "canvas": {{
        "use_canvas": true 또는 false,
        "canvas_guide": "Canvas 사용 시 구현 가이드 (미사용 시 null)"
    }},
    "no_image_strategy": "이미지 없이 UI를 구성하는 구체적인 전략 설명"
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

        design_spec = json.loads(raw)

    except json.JSONDecodeError as e:
        print(f"  ⚠️  Designer JSON 파싱 오류 → 기본 스펙 사용: {e}")
        if response:
            try:
                match = re.search(r"\{.*\}", response.text, re.DOTALL)
                if match:
                    design_spec = json.loads(match.group())
                else:
                    design_spec = _default_design_spec()
            except (json.JSONDecodeError, AttributeError):
                design_spec = _default_design_spec()
        else:
            design_spec = _default_design_spec()

    except Exception as e:
        print(f"  ⚠️  Designer 에러 → 기본 스펙 사용: {e}")
        design_spec = _default_design_spec()

    # design_spec.json을 codes에 추가해 output 디렉토리에 함께 저장
    codes = state.get("codes", {})
    codes["design_spec.json"] = json.dumps(design_spec, ensure_ascii=False, indent=2)

    state.update({
        "design_spec": design_spec,
        "codes": codes,
        "current_step": "FRONTEND_DEVELOP",
    })
    return state


def _has_frontend_ext(file_path: str) -> bool:
    ext = os.path.splitext(file_path.lower())[1]
    return ext in {".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}
