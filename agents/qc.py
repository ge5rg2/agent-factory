import google.generativeai as genai
import os
import ast
import json
import re
import subprocess
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

MAX_FIX_ITERATIONS = 2


# ── 파일 타입별 정적 검사 ──────────────────────────────────────────────────────

def _check_python(file_path: str, code: str) -> list:
    """AST 파싱으로 Python 문법 오류 검사."""
    try:
        ast.parse(code)
        return []
    except SyntaxError as e:
        return [f"[{file_path}] SyntaxError line {e.lineno}: {e.msg}"]


def _check_js(file_path: str, full_path: str) -> list:
    """node --check 로 JS 문법 오류 검사. node가 없으면 건너뜀."""
    try:
        result = subprocess.run(
            ["node", "--check", full_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return [f"[{file_path}] JS Error: {result.stderr.strip()}"]
        return []
    except FileNotFoundError:
        return []  # node 미설치 환경은 건너뜀
    except subprocess.TimeoutExpired:
        return [f"[{file_path}] JS check timed out"]


def _check_html(file_path: str, code: str) -> list:
    """필수 HTML 구조 태그 존재 여부 검사."""
    errors = []
    lower = code.lower()
    for tag in ("<html", "<head", "<body"):
        if tag not in lower:
            errors.append(f"[{file_path}] HTML: '{tag}>' 태그 누락")
    return errors


def _run_syntax_checks(output_dir: str, codes: dict) -> list:
    """output 디렉토리의 실제 파일을 대상으로 모든 정적 검사 실행."""
    errors = []
    for file_path in codes:
        full_path = os.path.join(output_dir, file_path)
        if not os.path.exists(full_path):
            continue
        with open(full_path, encoding="utf-8") as f:
            code = f.read()

        if file_path.endswith(".py"):
            errors.extend(_check_python(file_path, code))
        elif file_path.endswith(".js"):
            errors.extend(_check_js(file_path, full_path))
        elif file_path.endswith(".html"):
            errors.extend(_check_html(file_path, code))
    return errors


# ── Gemini 코드 리뷰 & 수정 ───────────────────────────────────────────────────

def _gemini_review_and_fix(model, prd: str, current_codes: dict, syntax_errors: list) -> dict:
    """전체 코드베이스를 Gemini로 리뷰하고, 이슈와 수정 코드 반환."""
    files_block = "\n".join(
        f"\n--- {path} ---\n{code}" for path, code in current_codes.items()
    )
    errors_block = (
        "\n=== 정적 검사에서 발견된 오류 ===\n" + "\n".join(syntax_errors)
        if syntax_errors else ""
    )

    prompt = f"""
당신은 시니어 코드 리뷰어입니다.
아래 코드베이스를 검토하고 문제를 발견하면 수정해주세요.

=== 기획서 (PRD) ===
{prd}
{errors_block}

=== 전체 코드베이스 ===
{files_block}

검토 항목:
1. 문법 오류 및 런타임 에러 가능성
2. import 누락 또는 잘못된 경로
3. 프론트엔드-백엔드 API 연동 불일치 (URL, 메서드, 필드명)
4. 기획서 대비 핵심 기능 누락

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이 JSON만):
{{
    "issues": ["발견된 문제 설명 1", "발견된 문제 설명 2"],
    "fixed_files": {{
        "수정이_필요한_파일경로": "수정된_전체_코드"
    }},
    "summary": "전체 QC 결과 한 줄 요약"
}}

수정이 필요 없는 파일은 fixed_files에 포함하지 마세요.
수정할 문제가 전혀 없으면 issues를 빈 배열로, fixed_files를 빈 객체로 반환하세요.
"""

    response = model.generate_content(prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw.strip())
    return json.loads(raw)


# ── README 생성 ───────────────────────────────────────────────────────────────

def _generate_readme(model, state: dict, output_dir: str, codes: dict) -> None:
    """QC 완료 후 output 디렉토리에 실행법이 담긴 README.md 생성."""

    file_tree_block = "\n".join(f"- {path}: {desc}" for path, desc in state.get("file_tree", {}).items())
    files_block = "\n".join(f"\n--- {path} ---\n{code}" for path, code in codes.items())

    prompt = f"""
당신은 기술 문서 작성 전문가입니다.
아래 정보를 바탕으로 이 프로젝트를 처음 보는 개발자가 바로 실행할 수 있는 README.md를 작성해주세요.

=== 기획서 (PRD) ===
{state.get("prd", "")}

=== 파일 구조 ===
{file_tree_block}

=== 전체 코드 ===
{files_block}

README.md에 반드시 포함할 항목:
1. 프로젝트 제목 및 한 줄 설명
2. 기술 스택 (언어, 프레임워크, DB 등)
3. 디렉토리 구조 (트리 형태)
4. 사전 요구사항 (Python 버전, node 여부 등)
5. 설치 및 실행 방법
   - 백엔드: 가상환경 생성, 패키지 설치(requirements 명시), 서버 실행 명령어
   - 프론트엔드: 별도 빌드 불필요한 경우 브라우저 열기 방법, 또는 serve 명령어
6. 주요 API 엔드포인트 (있는 경우)
7. 실행 확인 방법 (접속 URL 등)

반드시 마크다운 형식으로만 답변하세요. JSON이나 다른 형식은 사용하지 마세요.
"""

    try:
        response = model.generate_content(prompt)
        readme_content = response.text.strip()
        # 혹시 ```markdown 블록으로 감싸진 경우 제거
        if readme_content.startswith("```"):
            readme_content = re.sub(r'^```(?:markdown)?\n?', '', readme_content)
            readme_content = re.sub(r'\n?```$', '', readme_content.strip())

        readme_path = os.path.join(output_dir, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        print(f"  📄 README.md 생성 완료 → {readme_path}")
    except Exception as e:
        print(f"  ⚠️  README.md 생성 실패: {e}")


# ── QC Agent 메인 ─────────────────────────────────────────────────────────────

def qc_agent(state: dict) -> dict:
    model = genai.GenerativeModel('gemini-2.5-flash-lite')

    output_dir = os.path.join("output", state["project_name"])
    codes = dict(state.get("codes", {}))
    prd = state.get("prd", "")

    if not codes:
        state.update({"feedback": "검증할 코드가 없습니다.", "current_step": "ERROR"})
        return state

    all_issues = []
    total_fixed_files = set()

    for iteration in range(1, MAX_FIX_ITERATIONS + 1):
        print(f"  🔍 QC 검증 {iteration}회차...")

        # 1. output 디렉토리의 실제 파일 내용 읽기
        current_codes = {}
        for file_path in codes:
            full_path = os.path.join(output_dir, file_path)
            if os.path.exists(full_path):
                with open(full_path, encoding="utf-8") as f:
                    current_codes[file_path] = f.read()

        # 2. 정적 문법 검사
        syntax_errors = _run_syntax_checks(output_dir, codes)
        if syntax_errors:
            print(f"  ⚠️  문법 오류 {len(syntax_errors)}건 발견")
            for err in syntax_errors:
                print(f"      {err}")
        else:
            print(f"  ✅ 문법 검사 통과")

        # 3. Gemini 코드 리뷰
        try:
            result = _gemini_review_and_fix(model, prd, current_codes, syntax_errors)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  ⚠️  Gemini 리뷰 파싱 실패: {e}")
            break

        issues = result.get("issues", [])
        fixed_files = result.get("fixed_files", {})
        summary = result.get("summary", "")

        if issues:
            all_issues.extend(issues)
            print(f"  📋 이슈 {len(issues)}건: {', '.join(issues[:2])}{'...' if len(issues) > 2 else ''}")

        # 4. 수정 파일 적용
        if fixed_files:
            print(f"  🔧 {len(fixed_files)}개 파일 수정 적용 중...")
            for file_path, fixed_code in fixed_files.items():
                full_path = os.path.join(output_dir, file_path)
                if os.path.exists(full_path):
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(fixed_code)
                    codes[file_path] = fixed_code
                    total_fixed_files.add(file_path)
            print(f"  ✅ 수정 완료")
        else:
            print(f"  ✅ 추가 수정 필요 없음")
            # 이슈도 없고 수정도 없으면 조기 종료
            if not issues and not syntax_errors:
                print(f"\n  📝 README.md 생성 중...")
                _generate_readme(model, state, output_dir, codes)
                state.update({
                    "codes": codes,
                    "feedback": summary or "모든 파일 QC 통과",
                    "current_step": "DONE"
                })
                return state
            break  # 이슈는 있었지만 이미 직전 iteration에서 수정 완료

    # ── README 생성 & 최종 리포트 ─────────────────────────────────────────────
    print(f"\n  📝 README.md 생성 중...")
    _generate_readme(model, state, output_dir, codes)

    final_errors = _run_syntax_checks(output_dir, codes)

    report_lines = ["=== QC 최종 리포트 ==="]

    if all_issues:
        report_lines.append(f"\n발견된 이슈 ({len(all_issues)}건):")
        for i, issue in enumerate(all_issues, 1):
            report_lines.append(f"  {i}. {issue}")
    else:
        report_lines.append("\n이슈 없음")

    if total_fixed_files:
        report_lines.append(f"\n자동 수정된 파일 ({len(total_fixed_files)}개):")
        for f in sorted(total_fixed_files):
            report_lines.append(f"  - {f}")

    if final_errors:
        report_lines.append(f"\n⚠️  잔여 오류 ({len(final_errors)}건):")
        for err in final_errors:
            report_lines.append(f"  {err}")
    else:
        report_lines.append("\n✅ 최종 문법 검사 통과")

    state.update({
        "codes": codes,
        "feedback": "\n".join(report_lines),
        "current_step": "DONE"
    })
    return state
