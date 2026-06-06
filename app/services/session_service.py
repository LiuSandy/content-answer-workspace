from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import OUTPUT_DIR
from ..models import SessionPayload, WorkflowResult


def save_session(payload: SessionPayload) -> str:
    """保存前端提交的会话数据；这样用户编辑后的问题和回答可以作为本地 JSON 恢复。"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat().replace(":", "-")
    file_path = OUTPUT_DIR / f"manual-session-{timestamp}.json"
    file_path.write_text(payload.model_dump_json(indent=2, by_alias=True), "utf-8")
    return str(file_path)


def save_workflow_result(result: WorkflowResult) -> dict[str, str]:
    """保存完整工作流结果；这样 CLI 执行采集和生成后能产出可追踪的本地文件。"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_label = datetime.now().strftime("%Y-%m-%d")
    report_path = OUTPUT_DIR / f"workflow-daily-{date_label}.md"
    json_path = OUTPUT_DIR / f"workflow-daily-{date_label}.json"
    report_path.write_text("# Workflow result\n", "utf-8")
    json_path.write_text(result.model_dump_json(indent=2, by_alias=True), "utf-8")
    return {"reportPath": str(report_path), "jsonPath": str(json_path)}


def read_latest_session() -> dict[str, Any] | None:
    """读取最近一次 JSON 会话；这样前端初始化时可以恢复最新保存状态。"""

    if not OUTPUT_DIR.exists():
        return None
    json_files = sorted(OUTPUT_DIR.glob("*.json"), reverse=True)
    if not json_files:
        return None
    return json.loads(json_files[0].read_text("utf-8"))


def cookie_status(cookie_path_value: str) -> dict[str, bool]:
    """检查 cookie 文件配置和存在状态；这样采集前可以判断知乎请求凭据是否可用。"""

    configured = bool(cookie_path_value)
    loaded = bool(cookie_path_value and Path(cookie_path_value).exists())
    return {"configured": configured, "loaded": loaded}
