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


def _is_frontend_file(file_path: str) -> bool:
    """파일이 프론트엔드 담당인지 판별."""
    normalized = file_path.replace("\\", "/").lower()
    ext = os.path.splitext(normalized)[1]
    if ext in _FRONTEND_EXTENSIONS:
        return True
    for prefix in _FRONTEND_DIR_PREFIXES:
        if normalized.startswith(prefix + "/"):
            return True
    return False


def frontend_agent(state: dict) -> dict:
    """프론트엔드 파일을 생성하는 전문 에이전트.

    designer_agent가 생성한 design_spec을 참조하여
    Tailwind CSS 기반 UI와 HTML5 Canvas 컴포넌트를 구현합니다.
    이미지 에셋 없이 CSS 도형과 유니코드 문자만으로 UI를 구성합니다.
    """
    prd = state.get("prd", "")
    file_tree = state.get("file_tree", {})
    design_spec = state.get("design_spec", {})

    fe_files = {path: desc for path, desc in file_tree.items() if _is_frontend_file(path)}

    if not fe_files:
        state.update({"current_step": "BACKEND_DEVELOP"})
        return state

    codes = state.get("codes", {})
    all_files = "\n".join(f"- {path}: {desc}" for path, desc in file_tree.items())
    design_spec_str = json.dumps(design_spec, ensure_ascii=False, indent=2)

    use_canvas = design_spec.get("canvas", {}).get("use_canvas", False)
    canvas_guide = design_spec.get("canvas", {}).get("canvas_guide", "")
    no_image_strategy = design_spec.get("no_image_strategy", "CSS 도형과 유니코드 문자 활용")

    theme = design_spec.get("theme", {})
    components = design_spec.get("components", {})

    for file_path, file_description in fe_files.items():
        print(f"  🎨  FE 생성 중: {file_path}")

        existing_codes_context = ""
        if codes:
            existing_codes_context = "\n\n=== 이미 생성된 파일들 ===\n"
            for existing_path, existing_code in codes.items():
                if existing_path != "design_spec.json":
                    existing_codes_context += f"\n--- {existing_path} ---\n{existing_code}\n"

        canvas_section = ""
        if use_canvas:
            canvas_section = f"""
Canvas 구현 가이드:
{canvas_guide}
"""

        prompt = f"""
당신은 시니어 프론트엔드 개발자입니다.
아래 기획서와 디자인 스펙을 바탕으로 "{file_path}" 파일의 완전한 코드를 작성하세요.

=== 기획서 (PRD) ===
{prd}

=== 디자인 스펙 ===
{design_spec_str}

=== 전체 파일 구조 ===
{all_files}
{existing_codes_context}

=== 현재 작성할 파일 ===
파일 경로: {file_path}
파일 역할: {file_description}

요구사항:
1. 실제로 실행 가능한 완전한 코드를 작성하세요
2. Tailwind CSS는 CDN으로 로드 (`<script src="https://cdn.tailwindcss.com"></script>`)
3. 디자인 스펙의 테마 색상과 컴포넌트 클래스를 그대로 적용하세요
   - primary 버튼: {components.get("button_primary", "")}
   - card: {components.get("card", "")}
   - input: {components.get("input", "")}
4. [매우 중요] 이미지 파일(img 태그 src, background-image url()) 절대 사용 금지
   No-Image 전략: {no_image_strategy}
   - 아이콘: 유니코드 문자 또는 CSS 도형으로 대체
   - 배경: gradient, solid color 사용
   - 로고/이미지 영역: border-radius + background-color로 placeholder 구성
5. HTML5 Canvas 사용: {'예 - ' + canvas_guide if use_canvas else '아니오 (CSS 레이아웃만 사용)'}
{canvas_section}
6. 백엔드 API 연동: fetch API 사용, baseURL = 'http://localhost:8000'
7. 반응형 레이아웃 (모바일 우선, Tailwind 반응형 프리픽스 사용)
8. 주석 최소화, 코드 자체가 명확하도록 작성

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
            codes[file_path] = f"<!-- 생성 실패: {e} -->"

    state.update({
        "codes": codes,
        "current_step": "BACKEND_DEVELOP",
    })
    return state
