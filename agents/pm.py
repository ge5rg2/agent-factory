from google import genai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)


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
5. project_type 판별 규칙 (반드시 정확히 판별):
   - "frontend_only": 게임, SPA, 랜딩페이지 등 순수 프론트엔드 → Python 파일, requirements.txt 포함 금지
   - "fullstack": REST API + UI → backend/ + frontend/ 구조, requirements.txt 포함
   - "backend_only": CLI, 데이터 처리 등 순수 백엔드
6. interface_contracts: 여러 파일에서 참조되는 클래스/함수의 공개 API 계약
   - 형식: {{ "파일경로": "class ClassName {{ method1(param: type): returnType; method2(): void; }}" }}
   - 파일 간 인터페이스 불일치가 런타임 에러의 주요 원인입니다. 모든 주요 클래스에 계약 작성 필수
   - 예시: {{ "src/map.js": "class Map {{ loadData(data): void; isWalkable(x,y,size): bool; getGrid(): number[][]; }}" }}

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "project_name": "doom_fps_game",
    "project_type": "frontend_only",
    "prd": "기획 상세 내용 - 반드시 문자열로",
    "file_tree": {{
        "index.html": "메인 HTML 진입점",
        "src/game.js": "게임 루프 및 상태 관리",
        "src/utils/vector2.js": "2D 벡터 수학 유틸리티 클래스"
    }},
    "interface_contracts": {{
        "src/map.js": "class Map {{ loadData(data): void; isWalkable(x,y,size): bool; getGrid(): number[][]; getWidth(): int; getHeight(): int; }}",
        "src/player.js": "class Player {{ constructor(x,y,angle): void; update(deltaTime,map): void; takeDamage(amount): void; isAlive(): bool; getPosition(): {{x,y}}; }}"
    }}
}}
"""

    response = None
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt
        )
        raw = response.text.strip()

        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw.strip())

        result = json.loads(raw)

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

        state.update({
            "project_name": result.get("project_name", "mvp_project"),
            "project_type": project_type,
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
            "prd": "",
            "file_tree": {},
            "interface_contracts": {},
            "codes": {},
            "feedback": f"에러: {str(e)}",
            "current_step": "ERROR"
        })
        return state


def pm_upgrade_agent(state: dict, upgrade_request: str) -> dict:
    """기존 프로젝트를 분석하여 고도화 델타 계획을 수립하는 에이전트."""
    existing_prd = state.get("prd", "")
    existing_file_tree = state.get("file_tree", {})
    existing_codes = state.get("codes", {})

    file_list = "\n".join(f"- {path}: {desc}" for path, desc in existing_file_tree.items())

    preview_files = [
        p for p in existing_codes
        if p.endswith((".py", ".js", ".html", ".ts")) and not p.startswith(".")
    ][:8]
    code_preview = ""
    for path in preview_files:
        lines = existing_codes[path].splitlines()[:25]
        code_preview += f"\n--- {path} (첫 {len(lines)}줄) ---\n" + "\n".join(lines) + "\n"

    prompt = f"""
당신은 MVP 전문 기획자(PM)입니다.
기존 프로젝트에 새 기능을 추가하거나 수정하는 고도화 계획을 수립해주세요.

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

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "updated_prd": "업데이트된 기획서 전체 (기존 내용 + 새 기능 반영)",
    "delta_file_tree": {{
        "수정이_필요한_파일_경로": "이 파일에서 무엇을 변경할지 설명",
        "새로_추가할_파일_경로": "이 새 파일의 역할 설명"
    }},
    "change_summary": "고도화 변경사항 한 줄 요약 (한국어)"
}}
"""

    response = None
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw.strip())

        result = json.loads(raw)

        delta_file_tree = result.get("delta_file_tree", {})
        if any(isinstance(v, dict) for v in delta_file_tree.values()):
            delta_file_tree = _flatten_file_tree(delta_file_tree)
        delta_file_tree = {k: v for k, v in delta_file_tree.items() if not k.endswith("/")}

        updated_prd = result.get("updated_prd", existing_prd)
        if isinstance(updated_prd, dict):
            updated_prd = json.dumps(updated_prd, ensure_ascii=False, indent=2)

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
