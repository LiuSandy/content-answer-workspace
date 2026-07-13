"""Settings API 路由；统一暴露配置读写端点，前端设置页通过这些端点读取和修改所有运行时配置。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...services.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])
_service = SettingsService()


# ── 请求体模型 ──────────────────────────────────────────────────────────────

class LlmSettingsPayload(BaseModel):
    """LLM 配置更新请求体。"""
    base_url: str = Field(alias="baseUrl", default="")
    model: str = ""
    api_key: str | None = Field(alias="apiKey", default=None)

    model_config = {"populate_by_name": True}


class CollectSettingsPayload(BaseModel):
    """采集默认值更新请求体。"""
    default_platform: str | None = Field(alias="defaultPlatform", default=None)
    max_push_count: int | None = Field(alias="maxPushCount", default=None)
    sort_modes: list[str] | None = Field(alias="sortModes", default=None)
    user_agent: str | None = Field(alias="userAgent", default=None)
    skip_answer_generation: bool | None = Field(alias="skipAnswerGeneration", default=None)

    model_config = {"populate_by_name": True}


class PublishSettingsPayload(BaseModel):
    """发布配置更新请求体。"""
    test_mode: bool | None = Field(alias="testMode", default=None)
    official_account_name: str | None = Field(alias="officialAccountName", default=None)
    cta_text: str | None = Field(alias="ctaText", default=None)

    model_config = {"populate_by_name": True}




class AgentReachPlatformsPayload(BaseModel):
    """Agent-Reach 启用平台列表更新请求体。"""
    enabled_platforms: list[str] = Field(alias="enabledPlatforms", default_factory=list)

    model_config = {"populate_by_name": True}


class GroqKeyPayload(BaseModel):
    """Groq API Key 更新请求体。"""
    key: str = ""


class TopicPayload(BaseModel):
    """单个主题的创建/更新请求体。"""
    id: str = ""
    name: str = ""
    keywords: list[str] = Field(default_factory=list)
    expanded_hints: list[str] = Field(alias="expandedHints", default_factory=list)

    model_config = {"populate_by_name": True}


# ── 端点实现 ──────────────────────────────────────────────────────────────

@router.get("")
async def get_settings() -> JSONResponse:
    """返回全量配置（API Key 脱敏为 sk-***...***）。"""
    return JSONResponse({"ok": True, "data": _service.get_all()})


@router.post("/llm")
async def update_llm(payload: LlmSettingsPayload) -> JSONResponse:
    """更新 LLM 配置（baseUrl / model / apiKey）。"""
    try:
        _service.update_llm(payload.base_url, payload.model)
        if payload.api_key is not None:
            _service.update_api_key(payload.api_key)
        return JSONResponse({"ok": True})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/collect")
async def update_collect(payload: CollectSettingsPayload) -> JSONResponse:
    """更新采集默认值。"""
    try:
        data: dict[str, Any] = {}
        if payload.default_platform is not None:
            data["defaultPlatform"] = payload.default_platform
        if payload.max_push_count is not None:
            data["maxPushCount"] = payload.max_push_count
        if payload.sort_modes is not None:
            data["sortModes"] = payload.sort_modes
        if payload.user_agent is not None:
            data["userAgent"] = payload.user_agent
        if payload.skip_answer_generation is not None:
            data["skipAnswerGeneration"] = payload.skip_answer_generation
        _service.update_collect(data)
        return JSONResponse({"ok": True})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/publish")
async def update_publish(payload: PublishSettingsPayload) -> JSONResponse:
    """更新发布配置。"""
    try:
        data: dict[str, Any] = {}
        if payload.test_mode is not None:
            data["testMode"] = payload.test_mode
        if payload.official_account_name is not None:
            data["officialAccountName"] = payload.official_account_name
        if payload.cta_text is not None:
            data["ctaText"] = payload.cta_text
        _service.update_publish(data)
        return JSONResponse({"ok": True})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e




@router.get("/agent-reach/status")
async def get_agent_reach_status() -> JSONResponse:
    """调用 agent-reach doctor --json，返回各平台健康状态。"""
    result = _service.get_agent_reach_status()
    return JSONResponse(result)


@router.post("/agent-reach/platforms")
async def update_agent_reach_platforms(payload: AgentReachPlatformsPayload) -> JSONResponse:
    """更新启用平台列表。"""
    try:
        _service.update_agent_reach_config(payload.enabled_platforms)
        return JSONResponse({"ok": True})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/agent-reach/groq-key")
async def configure_groq_key(payload: GroqKeyPayload) -> JSONResponse:
    """配置 Groq API Key。"""
    try:
        _service.configure_groq_key(payload.key)
        return JSONResponse({"ok": True})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


class TwitterAuthPayload(BaseModel):
    """Twitter 认证字段更新请求体。"""
    auth_token: str = Field(alias="authToken", default="")
    ct0: str = ""

    model_config = {"populate_by_name": True}


@router.get("/agent-reach/twitter-auth")
async def get_twitter_auth() -> JSONResponse:
    """返回 Twitter 认证配置状态（脱敏）。"""
    return JSONResponse({
        "ok": True,
        "data": {
            **_service.get_twitter_auth(),
            "configured": _service.get_twitter_configured(),
        },
    })


@router.post("/agent-reach/twitter-auth")
async def save_twitter_auth(payload: TwitterAuthPayload) -> JSONResponse:
    """保存 TWITTER_AUTH_TOKEN 和 TWITTER_CT0 到 .env；twitter-cli 通过这两个变量认证。"""
    try:
        _service.save_twitter_auth(payload.auth_token, payload.ct0)
        return JSONResponse({"ok": True})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/topics")
async def get_topics() -> JSONResponse:
    """返回主题列表（回落到默认主题）。"""
    return JSONResponse({"ok": True, "data": _service.get_topics()})


@router.post("/topics")
async def create_topic(payload: TopicPayload) -> JSONResponse:
    """新增主题。"""
    try:
        topics = _service.get_topics()
        if any(t.get("id") == payload.id for t in topics):
            raise HTTPException(status_code=400, detail=f"主题 ID '{payload.id}' 已存在。")
        topics.append(payload.model_dump(by_alias=True))
        _service.save_topics(topics)
        return JSONResponse({"ok": True, "data": topics})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/topics/{topic_id}")
async def update_topic(topic_id: str, payload: TopicPayload) -> JSONResponse:
    """编辑主题。"""
    try:
        topics = _service.get_topics()
        idx = next((i for i, t in enumerate(topics) if t.get("id") == topic_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"主题 '{topic_id}' 不存在。")
        topics[idx] = {**payload.model_dump(by_alias=True), "id": topic_id}
        _service.save_topics(topics)
        return JSONResponse({"ok": True, "data": topics})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: str) -> JSONResponse:
    """删除主题。"""
    try:
        topics = _service.get_topics()
        filtered = [t for t in topics if t.get("id") != topic_id]
        if len(filtered) == len(topics):
            raise HTTPException(status_code=404, detail=f"主题 '{topic_id}' 不存在。")
        _service.save_topics(filtered)
        return JSONResponse({"ok": True, "data": filtered})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/restart")
async def restart_server() -> JSONResponse:
    """重启后端进程（os.execv）；此请求发出后连接断开属正常现象，前端需轮询 /api/health。"""
    import asyncio
    import threading

    def _do_restart() -> None:
        import time
        time.sleep(0.3)
        _service.restart_server()

    thread = threading.Thread(target=_do_restart, daemon=True)
    thread.start()
    return JSONResponse({"ok": True, "message": "重启中，请稍候..."})
