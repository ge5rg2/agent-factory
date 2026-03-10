from google import genai
import os
import json
import re
from dotenv import load_dotenv
from agents.utils import staff_log, build_log

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)

_FE_MODEL = os.getenv("FE_MODEL", "gemini-2.5-flash")

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


def _build_game_domain_section(design_spec: dict) -> str:
    """GAME 도메인 전용 Canvas + Pixel Sprite 렌더링 가이드를 생성합니다."""
    canvas = design_spec.get("canvas", {})
    canvas_guide = canvas.get("canvas_guide", "requestAnimationFrame 기반 게임 루프 사용")
    pixel_sprites = design_spec.get("pixel_sprites", {})
    color_palette = pixel_sprites.get("color_palette", {"0": "transparent", "1": "#4ade80"})
    sprite_scale = pixel_sprites.get("sprite_scale", 8)

    sprite_names = [k for k in pixel_sprites if k not in ("color_palette", "sprite_scale")]
    sprite_list = ", ".join(sprite_names) if sprite_names else "(스프라이트 없음)"

    pixel_renderer_code = """
// ── 픽셀 스프라이트 렌더러 (No-Image Engine) ──────────────────────────
// design_spec.json의 pixel_sprites 데이터를 Canvas에 직접 그립니다.
// 사용법: drawSprite(ctx, sprites.player, x, y, palette, scale)
function drawSprite(ctx, sprite, x, y, palette, scale) {
    sprite.forEach((row, sy) => {
        row.forEach((colorKey, sx) => {
            const color = palette[String(colorKey)];
            if (!color || color === 'transparent') return;
            ctx.fillStyle = color;
            ctx.fillRect(x + sx * scale, y + sy * scale, scale, scale);
        });
    });
}
"""

    return f"""
=== [GAME 도메인] Canvas + Pixel Sprite 렌더링 전략 ===

렌더링 방식: HTML5 Canvas API + requestAnimationFrame 게임 루프
절대 금지: DOM 조작 방식(innerHTML, createElement) — Canvas 렌더링만 사용하세요

Canvas 구현 가이드: {canvas_guide}

[No-Image Pixel Sprites]
design_spec.json의 pixel_sprites에는 이미 픽셀 데이터가 정의되어 있습니다.
이미지 파일을 생성/참조하지 말고, 이 2D 배열 데이터를 Canvas에 직접 렌더링하세요.

사용 가능한 스프라이트: {sprite_list}
컬러 팔레트: {json.dumps(color_palette, ensure_ascii=False)}
스프라이트 스케일: {sprite_scale}px per pixel

픽셀 렌더러 구현 패턴 (이 함수를 반드시 구현하세요):
{pixel_renderer_code}

pixel_sprites 데이터를 로드하는 방법:
- design_spec.json을 fetch로 로드하거나
- HTML 파일의 <script>에 직접 인라인으로 embed하세요 (서버 없는 경우)

게임 루프 구조:
```
function gameLoop(timestamp) {{
    const dt = (timestamp - lastTime) / 1000;
    lastTime = timestamp;
    update(dt);
    render(ctx);
    requestAnimationFrame(gameLoop);
}}
```
"""


def _build_app_domain_section(design_spec: dict) -> str:
    """APP 도메인 전용 DOM + Lucide 아이콘 렌더링 가이드를 생성합니다."""
    ui_components = design_spec.get("ui_components", {})
    theme = design_spec.get("theme", {})

    components_desc = "\n".join(
        f"  - {name}: icon={comp.get('icon','?')}, tailwind={comp.get('tailwind','')}, desc={comp.get('description','')}"
        for name, comp in ui_components.items()
        if isinstance(comp, dict)
    ) or "  (ui_components 없음)"

    return f"""
=== [APP 도메인] DOM + Tailwind + Lucide 렌더링 전략 ===

렌더링 방식: DOM 조작 (innerHTML, createElement, querySelector) + 이벤트 리스너
절대 금지: Canvas API, requestAnimationFrame 게임 루프 — DOM 방식만 사용하세요

[UI Components 명세]
design_spec.json에 정의된 UI 컴포넌트를 DOM으로 구현하세요:
{components_desc}

Lucide 아이콘 사용법 (CDN):
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
HTML에 아이콘 삽입: <i data-lucide="Menu"></i>
JS에서 초기화: lucide.createIcons();

Tailwind CSS CDN: <script src="https://cdn.tailwindcss.com"></script>

테마 색상 참고:
- Primary: {theme.get('primary', 'blue-500')}
- Background: {theme.get('background', 'gray-50')}
- Text: {theme.get('text_primary', 'gray-900')}

DOM 컴포넌트 패턴:
```javascript
// 재사용 가능한 컴포넌트 함수로 구현
function createCard(title, content) {{
    const card = document.createElement('div');
    card.className = 'bg-white rounded-xl shadow-md p-6 hover:shadow-lg transition-shadow';
    card.innerHTML = `<h3 class="font-bold text-lg">${{title}}</h3><p>${{content}}</p>`;
    return card;
}}
```
"""


def _generate_planning_thought(prd: str, fe_files: dict, domain: str, model: str) -> str:
    """파일 생성 루프 전에 프론트엔드 개발 계획을 요약하는 단일 LLM 호출."""
    files_list = ", ".join(fe_files.keys())
    prompt = f"""당신은 시니어 프론트엔드 개발자입니다.
아래 프로젝트의 프론트엔드 개발 전략을 1-2문장으로 설명하세요.

도메인: {domain} ({"게임/Canvas 기반" if domain == "GAME" else "웹 앱/DOM 기반"})
생성할 파일: {files_list}
기획 요약: {prd[:400]}

반드시 아래 JSON 형식으로만 답변하세요:
{{"thought": "이 프론트엔드 작업의 핵심 전략과 선택 이유 (1-2문장)"}}"""
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())
        return json.loads(raw).get("thought", "")
    except Exception:
        return ""


def frontend_agent(state: dict) -> dict:
    """프론트엔드 파일을 생성하는 전문 에이전트.

    v1.1.0-Core 도메인별 특화:
    - GAME: Canvas + pixel_sprites 기반 No-Image 렌더링 코드 생성
    - APP: DOM + Tailwind + Lucide 아이콘 기반 UI 컴포넌트 코드 생성
    interface_contracts를 활용해 파일 간 API 일관성을 보장합니다.
    """
    prd = state.get("prd", "")
    file_tree = state.get("file_tree", {})
    design_spec = state.get("design_spec", {})
    interface_contracts = state.get("interface_contracts", {})
    project_domain = state.get("project_domain", design_spec.get("project_domain", "APP"))

    fe_files = {path: desc for path, desc in file_tree.items() if _is_frontend_file(path)}

    if not fe_files:
        state.update({"current_step": "BACKEND_DEVELOP"})
        return state

    codes = state.get("codes", {})
    all_files = "\n".join(f"- {path}: {desc}" for path, desc in file_tree.items())
    design_spec_str = json.dumps(design_spec, ensure_ascii=False, indent=2)

    is_game = project_domain == "GAME"

    # 도메인별 렌더링 가이드 섹션 빌드
    if is_game:
        domain_section = _build_game_domain_section(design_spec)
    else:
        domain_section = _build_app_domain_section(design_spec)

    theme = design_spec.get("theme", {})
    components = design_spec.get("components", {})

    # 전체 인터페이스 계약 요약 (모든 파일)
    all_contracts_str = "\n".join(
        f"- {path}: {contract}" for path, contract in interface_contracts.items()
    ) if interface_contracts else "(인터페이스 계약 없음)"

    # 파일 루프 전 개발 계획 thought 생성
    thought = _generate_planning_thought(prd, fe_files, project_domain, _FE_MODEL)
    if thought:
        staff_log(state, "FRONTEND", thought)

    for file_path, file_description in fe_files.items():
        build_log(state, f"{'🎮' if is_game else '🎨'}  FE 생성 중: {file_path}")

        existing_codes_context = ""
        if codes:
            existing_codes_context = "\n\n=== 이미 생성된 파일들 ===\n"
            for existing_path, existing_code in codes.items():
                if existing_path != "design_spec.json":
                    existing_codes_context += f"\n--- {existing_path} ---\n{existing_code}\n"

        # 현재 파일의 인터페이스 계약
        current_contract = interface_contracts.get(file_path, "")

        # ── 파일 유형별 Anti-Smashing / ESM 규칙 ───────────────────────────
        is_html = file_path.endswith(".html")
        is_entry_js = file_path in ("src/index.js", "index.js")

        if is_html:
            file_specific_rules = """
=== [⛔ index.html 엄격 규칙 — Anti-Smashing] ===
이 파일은 순수한 진입점(entry point)입니다. 비즈니스 로직을 절대 포함하지 마세요.

✅ 허용:
  - HTML 구조 태그 (<html>, <head>, <body>, 시맨틱 태그)
  - CDN <link> / <script src="https://..."> (Tailwind, Lucide 등 외부 라이브러리)
  - <script type="module" src="src/index.js"></script> — 단 하나의 모듈 진입점
  - 최소한의 레이아웃 마크업 (빈 컨테이너 div 등)

❌ 절대 금지:
  - <script> 태그 안에 클래스, 함수, 변수 선언 등 비즈니스 로직
  - onclick=, onload=, onsubmit= 같은 인라인 이벤트 핸들러
  - 200줄 이상의 인라인 <script> 블록
  - window.xxx = ... 전역 변수 할당
  - import/export 없는 <script type="module"> 내 비즈니스 로직

올바른 예시:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>앱 제목</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="src/index.js"></script>
</body>
</html>
```"""
        elif is_entry_js:
            file_specific_rules = """
=== [📌 index.js 진입점 규칙] ===
이 파일은 앱 초기화 진입점입니다. 모듈을 조합하고 실행을 시작하는 역할만 합니다.

✅ 필수 패턴:
  - 다른 모듈에서 필요한 것들을 import
  - 최상위 Game/App 클래스 인스턴스 생성 후 start()
  - DOMContentLoaded 또는 window.onload 이벤트로 진입점 보호

✅ 예시:
```javascript
import { Game } from './core/game.js';

window.addEventListener('DOMContentLoaded', () => {
  const game = new Game(document.getElementById('canvas'));
  game.start();
});
```

❌ 절대 금지:
  - 클래스/함수 정의를 이 파일에 직접 작성 (다른 파일에 분리하고 import할 것)
  - window.xxx = ... 전역 변수
  - 100줄 이상의 비즈니스 로직"""
        else:
            file_specific_rules = f"""
=== [📦 ESM 모듈 파일 규칙] ===
이 파일은 독립적인 ES Module입니다. 아래 규칙을 엄격히 준수하세요.

✅ 필수:
  - 공개 심볼은 반드시 export: `export class Foo`, `export function bar`, `export const BAZ`
  - 다른 모듈 의존: `import {{ X }} from './relative-path.js'` (상대경로 + .js 확장자 필수)
  - 클래스 상태는 this.xxx 인스턴스 변수로 관리
  - 의존 객체는 생성자 파라미터로 주입 받기 (DI 패턴)

❌ 절대 금지:
  - `window.xxx = ...` (전역 네임스페이스 오염)
  - 최상위 스코프 `var/let/const` 선언 (export 없이) — 이것도 전역 오염입니다
  - `require()`, `module.exports` (CommonJS 방식)
  - 다른 모듈의 내부 구현에 직접 접근 (계약된 public API만 사용)

올바른 예시:
```javascript
import {{ Map }} from './map.js';
import {{ Vector2 }} from '../utils/vector2.js';

export class Player {{
  constructor(map, config) {{  // 의존성 주입
    this.map = map;
    this.pos = new Vector2(config.startX, config.startY);
    this.speed = config.speed ?? 3;
  }}
  update(dt) {{ ... }}
  getPosition() {{ return this.pos; }}
}}
```"""

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

=== 인터페이스 계약 (반드시 준수) ===
이 파일이 반드시 구현해야 하는 API:
{current_contract or '(이 파일에 대한 계약 없음 — 자유롭게 설계)'}

프로젝트 전체 인터페이스 계약 (다른 파일에서 제공/기대하는 API):
{all_contracts_str}

[중요] 계약에 명시된 메서드/속성을 정확한 시그니처로 구현하세요.
[중요] 다른 파일의 메서드를 호출할 때는 계약에 명시된 것만 호출하세요.
[중요] 의존성 주입: 클래스 생성 시 계약에 명시된 생성자 파라미터를 반드시 전달하세요.
  예) new Player(map, config) — map과 config를 직접 생성해서 전달
{domain_section}
{file_specific_rules}

=== 현재 작성할 파일 ===
파일 경로: {file_path}
파일 역할: {file_description}

공통 요구사항:
1. 실제로 실행 가능한 완전한 코드를 작성하세요 (절대 잘리거나 생략하지 마세요)
2. [매우 중요] 이미지 파일(img 태그 src, background-image url()) 절대 사용 금지
3. [매우 중요 — Strict DI] 전역 변수 사용 절대 금지:
   - ❌ 금지: window.player, window.map, 최상위 let player, var game (export 없는 최상위 선언)
   - ✅ 필수: 모든 상태는 최상위 Game/App 클래스가 보유하고, 하위 인스턴스에 생성자로 전달
   - 예시: class Game {{ constructor() {{ this.map = new Map(LEVEL_1); this.player = new Player(this.map, config); }} }}
4. 주석 최소화, 코드 자체가 명확하도록 작성
5. 백엔드 API 연동 시: fetch API 사용, baseURL = 'http://localhost:8000'
{"6. Canvas 렌더링: pixel_sprites 데이터를 사용해 drawSprite 함수로 렌더링" if is_game else "6. Tailwind CDN + Lucide CDN 로드 후 lucide.createIcons() 호출"}
{"7. requestAnimationFrame 기반 게임 루프 필수" if is_game else "7. 반응형 레이아웃 (모바일 우선, Tailwind 반응형 프리픽스 사용)"}
{"8. 게임 루프 구조: update(dt) → render(ctx) → requestAnimationFrame" if is_game else "8. 컬러 팔레트: primary=" + theme.get("primary", "blue-500") + ", bg=" + theme.get("background", "gray-50")}

파일 확장자에 맞는 마크다운 코드 블록으로만 답변하세요. JSON 형식 사용 금지.
출력 형식 예시 (HTML 파일인 경우):
```html
<!DOCTYPE html>
<html>
... 전체 코드 ...
</html>
```

출력 형식 예시 (JS 파일인 경우):
```javascript
// 전체 코드
export class Game {{ ... }}
```

[필수] 코드 블록 앞뒤에 다른 텍스트나 설명을 추가하지 마세요.
[필수] 코드가 아무리 길어도 절대 생략하거나 잘라내지 마세요.
"""

        response = None
        try:
            response = client.models.generate_content(
                model=_FE_MODEL,
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
            codes[file_path] = f"<!-- 생성 실패: {e} -->"

    state.update({
        "codes": codes,
        "current_step": "BACKEND_DEVELOP",
    })
    return state
