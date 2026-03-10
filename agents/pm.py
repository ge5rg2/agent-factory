from google import genai
import os
import json
import re
from dotenv import load_dotenv
from agents.utils import staff_log

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)

_PM_MODEL = os.getenv("PM_MODEL", "gemini-2.5-flash")


def _flatten_file_tree(tree: dict, prefix: str = "") -> dict:
    """중첩된 dict 구조의 file_tree를 flat한 {파일경로: 설명} 형태로 변환."""
    result = {}
    for key, value in tree.items():
        path = f"{prefix}{key}" if not prefix else f"{prefix}/{key}"
        if isinstance(value, dict):
            result.update(_flatten_file_tree(value, path))
        elif isinstance(value, str):
            if not path.endswith("/"):
                result[path] = value
    return result


def pm_agent(state: dict):

    prompt = f"""
당신은 MVP 전문 기획자(PM)입니다.
사용자의 아이디어: {state['idea']}

위 아이디어를 구현하기 위한 최소 기능 제품(MVP)의 파일 구조를 정의해주세요.

필수 요구사항:
1. 기획서(PRD)는 한국어로 작성하되 문자열(string)로만 작성하세요
2. file_tree의 키는 반드시 실제 파일 경로(예: src/utils/vector2.js)여야 합니다. 디렉토리나 중첩 dict 금지
3. project_name은 영어 snake_case로 작성하세요 (예: doom_fps_game)
4. [핵심] 파일 의존성 완전성: 파일 A가 파일 B를 import/require한다면, 파일 B도 file_tree에 반드시 포함
   - 게임/그래픽 프로젝트: 수학/벡터 유틸리티 파일 필수 포함 (예: src/utils/vector2.js)
   - 모든 공통 유틸리티는 utils/ 또는 helpers/ 디렉토리에 분리하여 file_tree에 포함
   - 암묵적 의존성(파일 트리에 없는데 코드에서 import)은 절대 허용하지 않습니다
   - [Level-as-Code 규칙] 게임 맵/레벨 데이터는 절대로 .json 파일로 분리하지 마세요.
     * ❌ 금지: assets/data/map01.json, data/level1.json (fetch로 읽으면 런타임 에러 발생)
     * ✅ 필수: src/level_data.js 같은 JS 파일에 배열 상수로 직접 정의하여 import로 사용
     * 예시: export const LEVEL_1 = [[1,1,1],[1,0,1],[1,1,1]]; (숫자: 1=벽, 0=빈공간)
5. project_type 판별 규칙 (반드시 정확히 판별):
   - "frontend_only": 게임, SPA, 랜딩페이지 등 순수 프론트엔드 → Python 파일, requirements.txt 포함 금지
   - "fullstack": REST API + UI → backend/ + frontend/ 구조, requirements.txt 포함
   - "backend_only": CLI, 데이터 처리 등 순수 백엔드
6. project_domain 판별 규칙 (렌더링 전략을 결정하는 핵심 분류):
   - "GAME": 게임, 시뮬레이션, 물리 엔진, 그래픽 집약적 인터랙션 → Canvas API 기반 렌더링
     * GAME 특성: requestAnimationFrame 루프, 픽셀 단위 충돌 감지, 스프라이트/타일맵
     * GAME 파일 구조 예시: src/core/engine.js, src/entities/player.js, src/utils/vector2.js
   - "APP": 웹 앱, SPA, 대시보드, 도구, 랜딩페이지 → DOM + Event-driven 렌더링
     * APP 특성: CRUD 인터페이스, 폼/입력, 목록/테이블, 페이지 라우팅
     * APP 파일 구조 예시: src/components/layout.js, src/pages/home.js, src/utils/api.js
7. interface_contracts: 여러 파일에서 참조되는 클래스/함수의 공개 API 계약
   - 형식: {{ "파일경로": "class ClassName {{ constructor(dep1: Type, dep2: Type): void; method1(param: type): returnType; }}" }}
   - [의존성 주입 필수] 생성자에서 의존 객체를 명시적으로 받도록 설계:
     * GAME 예시: class Player {{ constructor(map: Map, config: object): void; update(dt: number): void; }}
     * GAME 예시: class Map {{ constructor(data: number[][]): void; isWalkable(x,y,size): bool; getGrid(): number[][]; }}
     * APP 예시: class ApiClient {{ constructor(baseUrl: string): void; get(endpoint: string): Promise; }}
   - 파일 간 인터페이스 불일치가 런타임 에러의 주요 원인입니다. 모든 주요 클래스에 계약 작성 필수
   - undefined 참조 에러를 원천 차단하려면 필요한 모든 의존성을 생성자 파라미터로 명시하세요
8. [빌드 도구 금지 원칙] 이 프로젝트는 빌드 과정 없이 브라우저/런타임에서 직접 실행됩니다
   - ❌ 절대 금지: webpack, vite, rollup, esbuild, parcel, tsc (TypeScript 컴파일러), babel, npm scripts
   - ❌ 절대 금지: package.json, node_modules, tsconfig.json (빌드 관련 파일 일체)
   - ✅ 프론트엔드: 브라우저 네이티브 ESM (ES Modules) 으로 직접 실행
   - ✅ React/Vue 필요 시: CDN import-map 또는 <script type="importmap"> 으로 CDN에서 로드
   - ✅ TypeScript 불필요: 순수 JavaScript (ES2022+) 사용
9. [God File 금지 원칙] 모든 로직을 index.html 또는 단일 파일에 몰아 넣지 마세요
   - ❌ 절대 금지: index.html 안에 200줄 이상의 <script> 인라인 비즈니스 로직
   - ❌ 절대 금지: 단일 app.js에 모든 클래스/함수 정의
   - ✅ 필수: 역할별로 파일 분리 — index.html은 진입점(entry point)만, 로직은 src/ 디렉토리 하위 파일들에
   - ✅ index.html 규칙: `<script type="module" src="src/index.js"></script>` 단 한 줄만 허용
   - ✅ src/index.js: 앱 초기화 진입점 역할만 (import로 모듈 조합), 100줄 이내 권장
10. [ESM 모듈 시스템] 모든 JS 파일은 ES Modules 방식을 사용합니다
    - ✅ 공개 심볼: `export class Foo`, `export function bar`, `export const BAZ`
    - ✅ 의존성 로드: `import {{ Foo }} from './foo.js'` (상대경로 + .js 확장자 필수)
    - ❌ 절대 금지: `window.Foo = ...` (전역 네임스페이스 오염)
    - ❌ 절대 금지: `var/let/const` 최상위 선언 (export 없이)
    - ❌ 절대 금지: `require()`, `module.exports` (CommonJS 방식)

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "thought": "이 프로젝트의 도메인 판별 이유와 파일 구조 설계 전략 (1-2문장)",
    "project_name": "doom_fps_game",
    "project_type": "frontend_only",
    "project_domain": "GAME",
    "prd": "기획 상세 내용 - 반드시 문자열로",
    "file_tree": {{
        "index.html": "진입점 HTML — <script type='module' src='src/index.js'> 단 한 줄만",
        "src/index.js": "앱 초기화 진입점 — Game 클래스 import 후 start()",
        "src/core/engine.js": "게임 루프 및 렌더링 엔진 (export class Engine)",
        "src/entities/player.js": "플레이어 엔티티 (export class Player, map/config DI)",
        "src/utils/vector2.js": "2D 벡터 수학 유틸리티 (export class Vector2)"
    }},
    "interface_contracts": {{
        "src/map.js": "class Map {{ constructor(levelData: number[][]): void; isWalkable(x: number, y: number, size: number): bool; getGrid(): number[][]; getWidth(): number; getHeight(): number; }}",
        "src/entities/player.js": "class Player {{ constructor(map: Map, config: {{startX: number, startY: number, fov: number}}): void; update(deltaTime: number): void; takeDamage(amount: number): void; isAlive(): bool; getPosition(): {{x: number, y: number}}; }}"
    }}
}}
"""

    response = None
    try:
        response = client.models.generate_content(
            model=_PM_MODEL,
            contents=prompt
        )
        raw = response.text.strip()

        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw.strip())

        result = json.loads(raw)

        thought = result.get("thought", "")
        if thought:
            staff_log(state, "PM", thought)

        file_tree = result.get("file_tree", {})
        if any(isinstance(v, dict) for v in file_tree.values()):
            file_tree = _flatten_file_tree(file_tree)
        file_tree = {k: v for k, v in file_tree.items() if not k.endswith("/")}

        prd = result.get("prd", "")
        if isinstance(prd, dict):
            prd = json.dumps(prd, ensure_ascii=False, indent=2)

        interface_contracts = result.get("interface_contracts", {})
        if not isinstance(interface_contracts, dict):
            interface_contracts = {}

        project_type = result.get("project_type", "fullstack")
        project_domain = result.get("project_domain", "APP")
        if project_domain not in ("GAME", "APP"):
            project_domain = "GAME" if any(
                kw in state.get("idea", "").lower()
                for kw in ("game", "게임", "fps", "rpg", "puzzle", "퍼즐", "simulation", "시뮬")
            ) else "APP"

        state.update({
            "project_name": result.get("project_name", "mvp_project"),
            "project_type": project_type,
            "project_domain": project_domain,
            "prd": prd,
            "file_tree": file_tree,
            "interface_contracts": interface_contracts,
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
                        "project_type": result.get("project_type", "fullstack"),
                        "project_domain": result.get("project_domain", "APP"),
                        "prd": prd,
                        "file_tree": file_tree,
                        "interface_contracts": result.get("interface_contracts", {}),
                        "codes": {},
                        "feedback": "",
                        "current_step": "FE_DEVELOP"
                    })
                    return state
            except (json.JSONDecodeError, AttributeError):
                pass

        state.update({
            "project_name": "mvp_project",
            "project_type": "fullstack",
            "project_domain": "APP",
            "prd": response.text if response else "",
            "file_tree": {},
            "interface_contracts": {},
            "codes": {},
            "feedback": "JSON 파싱 실패",
            "current_step": "ERROR"
        })
        return state

    except Exception as e:
        print(f"⚠️  에러 발생: {e}")
        state.update({
            "project_name": "mvp_project",
            "project_type": "fullstack",
            "project_domain": "APP",
            "prd": "",
            "file_tree": {},
            "interface_contracts": {},
            "codes": {},
            "feedback": f"에러: {str(e)}",
            "current_step": "ERROR"
        })
        return state


def pm_upgrade_agent(state: dict, upgrade_request: str) -> dict:
    """기존 프로젝트를 분석하여 고도화 델타 계획을 수립하는 에이전트.

    Safe-Update Logic:
    - 기존 렌더링 방식(Canvas Loop vs DOM Event)을 판별하고 보존합니다.
    - 변경이 필요한 파일만 델타로 반환하여 기존 엔진을 파괴하지 않습니다.
    """
    existing_prd = state.get("prd", "")
    existing_file_tree = state.get("file_tree", {})
    existing_codes = state.get("codes", {})
    project_domain = state.get("project_domain", "APP")

    file_list = "\n".join(f"- {path}: {desc}" for path, desc in existing_file_tree.items())

    # ── 기존 렌더링 방식 탐지 (Safe-Update를 위한 분석) ──────────────────────
    rendering_type = "unknown"
    has_raf = any(
        "requestAnimationFrame" in code or "gameLoop" in code or "game_loop" in code
        for code in existing_codes.values()
    )
    has_canvas = any(
        "getContext" in code or "ctx.draw" in code or "canvas" in code.lower()
        for code in existing_codes.values()
    )
    has_event_listener = any(
        "addEventListener" in code or "querySelector" in code
        for code in existing_codes.values()
    )
    if has_raf or has_canvas:
        rendering_type = "CANVAS_LOOP"
    elif has_event_listener:
        rendering_type = "DOM_EVENT"

    preview_files = [
        p for p in existing_codes
        if p.endswith((".py", ".js", ".html", ".ts")) and not p.startswith(".")
    ][:8]
    code_preview = ""
    for path in preview_files:
        lines = existing_codes[path].splitlines()[:25]
        code_preview += f"\n--- {path} (첫 {len(lines)}줄) ---\n" + "\n".join(lines) + "\n"

    rendering_note = {
        "CANVAS_LOOP": "기존 프로젝트는 Canvas + requestAnimationFrame 기반 게임 루프를 사용합니다. "
                       "새 기능은 이 루프 안에서 동작하도록 설계하고, DOM 이벤트 방식으로 대체하지 마세요.",
        "DOM_EVENT": "기존 프로젝트는 DOM + 이벤트 리스너 방식을 사용합니다. "
                     "새 기능도 DOM 조작과 이벤트 방식으로 구현하고, Canvas 루프를 추가하지 마세요.",
        "unknown": "기존 렌더링 방식을 판별할 수 없습니다. 기존 파일 구조와 일관성을 유지하세요.",
    }.get(rendering_type, "")

    prompt = f"""
당신은 MVP 전문 기획자(PM)입니다.
기존 프로젝트에 새 기능을 추가하거나 수정하는 고도화 계획을 수립해주세요.

=== 프로젝트 도메인 ===
{project_domain} ({"게임/그래픽 엔진" if project_domain == "GAME" else "웹 앱/SPA"})

=== [Safe-Update] 기존 렌더링 방식 ===
감지된 렌더링 타입: {rendering_type}
{rendering_note}

=== 기존 기획서 (PRD) ===
{existing_prd}

=== 기존 파일 구조 ===
{file_list or '(파일 없음)'}

=== 코드 미리보기 ===
{code_preview or '(없음)'}

=== 고도화 요청사항 ===
{upgrade_request}

분석 요령:
- 요청사항을 구현하기 위해 반드시 변경/추가해야 하는 파일만 delta_file_tree에 포함하세요
- 변경 없는 파일은 절대 포함하지 마세요
- 새 파일 추가 시에는 기존 구조와 일관성을 유지하세요
- [Safe-Update] 기존 렌더링 엔진(Canvas Loop 또는 DOM Event)을 파괴하지 마세요
- [Safe-Update] 기능 추가는 기존 방식의 확장이어야 하며, 방식 교체는 안됩니다

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "thought": "이 고도화 요청의 핵심 변경사항과 접근 전략 (1-2문장)",
    "updated_prd": "업데이트된 기획서 전체 (기존 내용 + 새 기능 반영)",
    "delta_file_tree": {{
        "수정이_필요한_파일_경로": "이 파일에서 무엇을 변경할지 설명",
        "새로_추가할_파일_경로": "이 새 파일의 역할 설명"
    }},
    "rendering_preserved": "기존 렌더링 방식을 어떻게 보존했는지 설명",
    "change_summary": "고도화 변경사항 한 줄 요약 (한국어)"
}}
"""

    response = None
    try:
        response = client.models.generate_content(
            model=_PM_MODEL,
            contents=prompt
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw.strip())

        result = json.loads(raw)

        thought = result.get("thought", "")
        if thought:
            staff_log(state, "PM", thought)

        delta_file_tree = result.get("delta_file_tree", {})
        if any(isinstance(v, dict) for v in delta_file_tree.values()):
            delta_file_tree = _flatten_file_tree(delta_file_tree)
        delta_file_tree = {k: v for k, v in delta_file_tree.items() if not k.endswith("/")}

        updated_prd = result.get("updated_prd", existing_prd)
        if isinstance(updated_prd, dict):
            updated_prd = json.dumps(updated_prd, ensure_ascii=False, indent=2)

        rendering_preserved = result.get("rendering_preserved", "")
        if rendering_preserved:
            print(f"  🔒 렌더링 보존: {rendering_preserved}")

        state.update({
            "prd": updated_prd,
            "file_tree": delta_file_tree,
            "feedback": result.get("change_summary", ""),
            "current_step": "DESIGNER",
        })
        return state

    except json.JSONDecodeError as e:
        print(f"⚠️  PM Upgrade JSON 파싱 오류: {e}")
        if response:
            try:
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    delta_file_tree = result.get("delta_file_tree", {})
                    if any(isinstance(v, dict) for v in delta_file_tree.values()):
                        delta_file_tree = _flatten_file_tree(delta_file_tree)
                    delta_file_tree = {k: v for k, v in delta_file_tree.items() if not k.endswith("/")}
                    state.update({
                        "prd": result.get("updated_prd", existing_prd),
                        "file_tree": delta_file_tree,
                        "feedback": result.get("change_summary", ""),
                        "current_step": "DESIGNER",
                    })
                    return state
            except (json.JSONDecodeError, AttributeError):
                pass

        state.update({
            "file_tree": {},
            "feedback": "업그레이드 계획 파싱 실패",
            "current_step": "ERROR",
        })
        return state

    except Exception as e:
        print(f"⚠️  PM Upgrade 에러: {e}")
        state.update({
            "file_tree": {},
            "feedback": f"에러: {str(e)}",
            "current_step": "ERROR",
        })
        return state
