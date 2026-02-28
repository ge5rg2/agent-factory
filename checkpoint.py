"""체크포인트 기반 작업 복구 (Fault Tolerance) 모듈.

파이프라인 각 단계 완료 시 AgentState를 JSON으로 기록하고,
비정상 종료 시 마지막 완료 지점부터 재가동할 수 있게 합니다.

디렉토리 구조:
  .agent_logs/
    active/      ← 진행 중인 작업 상태
    completed/   ← 정상 종료된 작업 아카이브
"""

import json
import os
import shutil
from datetime import datetime

_ACTIVE_DIR = ".agent_logs/active"
_COMPLETED_DIR = ".agent_logs/completed"

# 단계별 레이블 (화면 표시용)
PHASE_LABELS = {
    "PM_DONE":        "PM 기획 완료 → Designer 재개 가능",
    "DESIGNER_DONE":  "Designer 완료 → Frontend 재개 가능",
    "FRONTEND_DONE":  "Frontend 완료 → Backend 재개 가능",
    "BACKEND_DONE":   "Backend 완료 → 저장 & QC 재개 가능",
    "DISK_SAVED":     "저장 완료 → QC 재개 가능",
}


def save_checkpoint(state: dict, phase: str) -> str:
    """현재 AgentState를 active 디렉토리에 JSON으로 저장.

    같은 project_name이면 파일을 덮어씁니다 (항상 최신 상태 유지).
    Returns:
        저장된 체크포인트 파일 경로
    """
    os.makedirs(_ACTIVE_DIR, exist_ok=True)

    project_name = state.get("project_name") or "unknown"
    file_path = os.path.join(_ACTIVE_DIR, f"{project_name}.json")

    checkpoint_data = {
        "timestamp": datetime.now().isoformat(),
        "phase_completed": phase,
        "state": state,
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

    return file_path


def list_active_checkpoints() -> list[dict]:
    """active 디렉토리의 체크포인트 목록을 최신 순으로 반환.

    Returns:
        [{"file_path", "project_name", "phase_completed", "timestamp", "state"}, ...]
    """
    if not os.path.isdir(_ACTIVE_DIR):
        return []

    checkpoints = []
    for fname in os.listdir(_ACTIVE_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(_ACTIVE_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            checkpoints.append({
                "file_path": fpath,
                "project_name": data["state"].get("project_name", "unknown"),
                "phase_completed": data.get("phase_completed", "unknown"),
                "timestamp": data.get("timestamp", ""),
                "state": data["state"],
            })
        except (json.JSONDecodeError, KeyError):
            pass

    return sorted(checkpoints, key=lambda x: x["timestamp"], reverse=True)


def archive_checkpoint(file_path: str) -> None:
    """정상 종료 시 active 체크포인트를 completed 디렉토리로 이동."""
    if not file_path or not os.path.exists(file_path):
        return

    os.makedirs(_COMPLETED_DIR, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(file_path)
    name, ext = os.path.splitext(basename)
    dest = os.path.join(_COMPLETED_DIR, f"{name}_{ts}{ext}")

    shutil.move(file_path, dest)
    print(f"  📦 체크포인트 아카이브: {dest}")


def delete_checkpoint(file_path: str) -> None:
    """active 체크포인트 삭제 (재시도 포기 시 사용)."""
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
