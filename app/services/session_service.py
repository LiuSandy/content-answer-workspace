from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config.runtime import OUTPUT_DIR
from app.api.schemas.workflow import SessionPayload, WorkflowResult

SESSIONS_DIR = OUTPUT_DIR / "sessions"


def _session_file_path(session_id: str) -> Path:
    """返回指定 session 对应的文件路径；这样创建、读取、保存都基于同一套寻址规则。"""

    return SESSIONS_DIR / f"{session_id}.json"


def create_session() -> dict[str, str]:
    """创建一个新的空 session；这样对话页面点「新建对话」时能立刻拿到一个可用的 sessionId。"""

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex
    created_at = datetime.now().isoformat()
    payload = SessionPayload(sessionId=session_id, title="新对话", createdAt=created_at)
    _session_file_path(session_id).write_text(payload.model_dump_json(indent=2, by_alias=True), "utf-8")
    return {"sessionId": session_id, "title": payload.title, "createdAt": created_at}


def list_sessions() -> list[dict[str, str]]:
    """列出所有 session 的摘要信息；这样对话页面和工作区页面能渲染可切换的会话列表。"""

    if not SESSIONS_DIR.exists():
        return []
    summaries: list[dict[str, str]] = []
    for file_path in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        summaries.append(
            {
                "sessionId": data.get("sessionId") or file_path.stem,
                "title": data.get("title") or "新对话",
                "createdAt": data.get("createdAt") or "",
            }
        )
    return sorted(summaries, key=lambda item: item["createdAt"], reverse=True)


def read_session(session_id: str) -> dict[str, Any] | None:
    """按 ID 读取指定 session 的工作区数据；这样前端切换会话时能恢复对应的采集结果和回答。"""

    file_path = _session_file_path(session_id)
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text("utf-8"))


def save_session(payload: SessionPayload) -> str:
    """保存前端提交的会话数据；按 sessionId 落盘，重复保存覆盖同一份文件而不再新建时间戳文件。"""

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_id = payload.session_id or uuid.uuid4().hex
    data = payload.model_copy(update={"session_id": session_id})
    file_path = _session_file_path(session_id)
    file_path.write_text(data.model_dump_json(indent=2, by_alias=True), "utf-8")
    return str(file_path)


def delete_session(session_id: str) -> bool:
    """删除指定 session 的文件；返回 True 表示删除成功，False 表示文件不存在。"""

    file_path = _session_file_path(session_id)
    if not file_path.exists():
        return False
    file_path.unlink()
    return True


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
    """读取最近创建的一个 session；兼容旧版「只读最新一份」的调用方式。"""

    summaries = list_sessions()
    if not summaries:
        return None
    return read_session(summaries[0]["sessionId"])


def update_session_title(session_id: str, title: str) -> None:
    """更新指定 session 的标题；这样对话发出第一条消息后能自动生成有意义的会话名称。"""

    file_path = _session_file_path(session_id)
    if not file_path.exists():
        return
    data = json.loads(file_path.read_text("utf-8"))
    data["title"] = title
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def cookie_status(cookie_path_value: str) -> dict[str, bool]:
    """检查 cookie 文件配置和存在状态；这样采集前可以判断知乎请求凭据是否可用。"""

    configured = bool(cookie_path_value)
    loaded = bool(cookie_path_value and Path(cookie_path_value).exists())
    return {"configured": configured, "loaded": loaded}
