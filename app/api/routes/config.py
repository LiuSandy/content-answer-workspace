from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.runtime import get_workflow_config, load_env_file
from ...services.zhihu_service import get_default_topics, get_topic_preview

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config() -> JSONResponse:
    """返回前端初始化配置；这样工作台启动时能拿到默认主题和后端规范化后的工作流参数。"""

    load_env_file()
    return JSONResponse(
        {
            "ok": True,
            "data": {
                "topics": [get_topic_preview(topic).model_dump(by_alias=True) for topic in get_default_topics()],
                "workflow": get_workflow_config().model_dump(by_alias=True),
            },
        }
    )
