from google import genai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)

_DESIGNER_MODEL = os.getenv("DESIGNER_MODEL", "gemini-2.5-flash-lite")


def _default_design_spec(project_domain: str = "APP") -> dict:
    """파싱 실패 시 사용할 범용 기본 디자인 스펙."""
    base = {
        "project_domain": project_domain,
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
            "use_canvas": project_domain == "GAME",
            "canvas_guide": "requestAnimationFrame 기반 게임 루프 사용" if project_domain == "GAME" else None,
        },
        "no_image_strategy": "CSS 도형(border-radius, gradient, box-shadow)과 유니코드 이모지를 활용한 이미지 대체",
    }

    if project_domain == "GAME":
        base["pixel_sprites"] = {
            "player": [
                [0, 1, 1, 0],
                [1, 1, 1, 1],
                [0, 1, 1, 0],
                [0, 1, 0, 1],
            ],
            "wall_tile": [
                [2, 2, 2, 2],
                [2, 0, 0, 2],
                [2, 0, 0, 2],
                [2, 2, 2, 2],
            ],
            "color_palette": {
                "0": "transparent",
                "1": "#4ade80",
                "2": "#6b7280",
            },
            "sprite_scale": 8,
        }
    else:
        base["ui_components"] = {
            "navbar": {
                "tailwind": "flex items-center justify-between px-6 py-4 bg-white shadow-sm",
                "icon": "Menu",
                "description": "상단 네비게이션 바",
            },
            "hero": {
                "tailwind": "flex flex-col items-center justify-center py-20 bg-gradient-to-br from-blue-50 to-indigo-100",
                "icon": "Layout",
                "description": "히어로 섹션",
            },
            "card_grid": {
                "tailwind": "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 p-6",
                "icon": "Grid",
                "description": "카드 그리드 레이아웃",
            },
        }

    return base


def designer_agent(state: dict) -> dict:
    """UI/UX 디자인 스펙(design_spec.json)을 생성하는 에이전트.

    v1.1.0-Core No-Image Engine:
    - GAME 도메인: pixel_sprites (2D 픽셀 배열 + 컬러 팔레트) 생성
      → 외부 이미지 파일 없이 Canvas API로 직접 픽셀 렌더링
    - APP 도메인: ui_components (Tailwind 클래스 + Lucide 아이콘) 생성
      → DOM 기반 컴포넌트 렌더링 명세
    """
    idea = state.get("idea", "")
    prd = state.get("prd", "")
    file_tree = state.get("file_tree", {})
    project_domain = state.get("project_domain", "APP")
    fe_files = [p for p in file_tree if _has_frontend_ext(p)]

    is_game = project_domain == "GAME"

    if is_game:
        domain_prompt = f"""
=== GAME 도메인 - No-Image Pixel Strategy ===
이 프로젝트는 게임입니다. 이미지 파일 없이 Canvas API로 픽셀을 직접 렌더링합니다.

pixel_sprites 필드를 생성하세요:
- 각 스프라이트는 2D 숫자 배열입니다 (각 숫자는 color_palette 키에 대응)
- 0 = transparent (투명), 나머지 숫자는 color_palette에 정의한 색상
- 스프라이트 크기: 8×8 또는 16×16 (게임 캐릭터/타일에 적합한 크기)
- 프로젝트에 필요한 주요 스프라이트 3~6개를 생성하세요 (player, enemy, wall_tile, floor_tile, item 등)
- sprite_scale: 실제 Canvas 렌더링 시 각 픽셀을 몇 배로 확대할지 (8~16 권장)
- color_palette: 스프라이트에 사용된 숫자키 → 실제 CSS 색상값 (hex 또는 named)

Frontend 에이전트가 이 pixel_sprites 데이터로 Canvas에 직접 그립니다.
(예: sprite.forEach((row, y) => row.forEach((color, x) => {{ ctx.fillStyle = palette[color]; ctx.fillRect(x*scale, y*scale, scale, scale); }})))
"""
        domain_json_example = """
    "pixel_sprites": {
        "player": [
            [0, 0, 1, 1, 1, 0, 0, 0],
            [0, 1, 1, 1, 1, 1, 0, 0],
            [1, 1, 2, 1, 1, 2, 1, 0],
            [1, 1, 1, 1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1, 0, 0, 0],
            [0, 1, 0, 1, 1, 0, 1, 0],
            [1, 1, 0, 0, 0, 0, 1, 1],
            [0, 0, 0, 0, 0, 0, 0, 0]
        ],
        "wall_tile": [
            [3, 3, 3, 3, 3, 3, 3, 3],
            [3, 2, 2, 3, 3, 2, 2, 3],
            [3, 2, 2, 3, 3, 2, 2, 3],
            [3, 3, 3, 3, 3, 3, 3, 3],
            [3, 3, 2, 2, 2, 2, 3, 3],
            [3, 3, 2, 2, 2, 2, 3, 3],
            [3, 3, 3, 3, 3, 3, 3, 3],
            [3, 3, 3, 3, 3, 3, 3, 3]
        ],
        "color_palette": {
            "0": "transparent",
            "1": "#4ade80",
            "2": "#1e3a2f",
            "3": "#6b7280"
        },
        "sprite_scale": 8
    }"""
    else:
        domain_prompt = f"""
=== APP 도메인 - UI Component Strategy ===
이 프로젝트는 웹 앱입니다. DOM 기반으로 렌더링하며 Tailwind CSS와 Lucide 아이콘을 사용합니다.

ui_components 필드를 생성하세요:
- 프로젝트의 주요 UI 섹션/컴포넌트를 3~6개 정의하세요
- 각 컴포넌트: tailwind(CSS 클래스), icon(Lucide 아이콘 이름), description(역할 설명)
- Lucide 아이콘 예시: Home, Settings, User, Bell, Search, Plus, Edit, Trash, ChevronRight, ArrowLeft, ...
- Tailwind 클래스는 실제로 사용할 수 있는 조합이어야 합니다

Frontend 에이전트가 이 ui_components 데이터로 DOM 요소를 구성합니다.
"""
        domain_json_example = """
    "ui_components": {
        "navbar": {
            "tailwind": "flex items-center justify-between px-6 py-4 bg-white shadow-sm border-b border-gray-100",
            "icon": "Menu",
            "description": "상단 네비게이션 바 (로고 + 메뉴)"
        },
        "hero_section": {
            "tailwind": "flex flex-col items-center justify-center min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 text-center px-4",
            "icon": "Sparkles",
            "description": "메인 히어로 섹션"
        },
        "card_item": {
            "tailwind": "bg-white rounded-xl shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer border border-gray-100",
            "icon": "FileText",
            "description": "개별 아이템 카드"
        }
    }"""

    prompt = f"""
당신은 시니어 UI/UX 디자이너입니다.
아래 기획서를 바탕으로 프로젝트의 디자인 시스템을 정의해주세요.

=== 아이디어 ===
{idea}

=== 기획서 (PRD) ===
{prd}

=== 프로젝트 도메인 ===
{project_domain} ({"게임/그래픽" if is_game else "웹 앱/SPA"})

=== 프론트엔드 파일 목록 ===
{chr(10).join(f'- {p}' for p in fe_files) or '(없음)'}
{domain_prompt}

공통 디자인 원칙:
- 이미지 파일 에셋 절대 사용 금지 (img src, background-image url() 금지)
- {"Canvas API로 pixel_sprites 데이터를 직접 렌더링" if is_game else "Tailwind CSS CDN + DOM 조작으로 UI 구성"}
- 프로젝트 특성에 맞는 감성적인 컬러 팔레트 선택

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "project_domain": "{project_domain}",
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
        "font_stack": "CSS font-family 값",
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
        "use_canvas": {"true" if is_game else "false"},
        "canvas_guide": "{"Canvas 기반 게임 루프 구현 가이드" if is_game else "null"}"
    }},
    "no_image_strategy": "이미지 없이 UI를 구성하는 구체적인 전략 설명",
{domain_json_example}
}}
"""

    response = None
    try:
        response = client.models.generate_content(
            model=_DESIGNER_MODEL,
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
                    design_spec = _default_design_spec(project_domain)
            except (json.JSONDecodeError, AttributeError):
                design_spec = _default_design_spec(project_domain)
        else:
            design_spec = _default_design_spec(project_domain)

    except Exception as e:
        print(f"  ⚠️  Designer 에러 → 기본 스펙 사용: {e}")
        design_spec = _default_design_spec(project_domain)

    # project_domain이 누락된 경우 보완
    if "project_domain" not in design_spec:
        design_spec["project_domain"] = project_domain

    # GAME인데 pixel_sprites가 없으면 기본값 보완
    if is_game and "pixel_sprites" not in design_spec:
        design_spec["pixel_sprites"] = _default_design_spec("GAME")["pixel_sprites"]
        print(f"  ⚠️  pixel_sprites 누락 → 기본 스프라이트 삽입")

    # APP인데 ui_components가 없으면 기본값 보완
    if not is_game and "ui_components" not in design_spec:
        design_spec["ui_components"] = _default_design_spec("APP")["ui_components"]
        print(f"  ⚠️  ui_components 누락 → 기본 컴포넌트 삽입")

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
