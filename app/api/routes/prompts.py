from __future__ import annotations

import logging
from pathlib import Path
import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...prompts.registry import prompt_registry
from ...prompts.schemas import PromptSchema

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompts", tags=["prompts"])


# 自定义 YAML Dumper 用于保持多行字符串的 Block Style (|) 格式且不对中文转义
class BlockStyleDumper(yaml.SafeDumper):
    pass


def str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


BlockStyleDumper.add_representer(str, str_presenter)


class PromptDetailResponse(BaseModel):
    id: str
    system_prompt: str = Field(..., serialization_alias="systemPrompt")
    user_prompt: str = Field(..., serialization_alias="userPrompt")
    file_path: str = Field(..., serialization_alias="filePath")


class UpdatePromptRequest(BaseModel):
    system_prompt: str = Field(..., alias="systemPrompt")
    user_prompt: str | None = Field(default=None, alias="userPrompt")


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: str) -> JSONResponse:
    """获取指定提示词核心的 System Prompt 与 User Prompt 内容。"""
    try:
        # 获取源文件路径
        if prompt_id not in prompt_registry._sources:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        file_path = Path(prompt_registry._sources[prompt_id])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Prompt file not found on disk")
        
        raw_content = file_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw_content)
        if not isinstance(parsed, dict) or "messages" not in parsed:
            raise ValueError("Invalid prompt YAML structure")

        messages = parsed.get("messages", [])
        system_msg = next((m for m in messages if m.get("role") == "system"), None)
        user_msg = next((m for m in messages if m.get("role") == "user"), None)

        if not system_msg:
            raise ValueError("Prompt template must contain a system message")

        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "id": prompt_id,
                    "systemPrompt": system_msg.get("content", ""),
                    "userPrompt": user_msg.get("content", "") if user_msg else "",
                    "filePath": str(file_path),
                },
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to read prompt %s: %s", prompt_id, e)
        return JSONResponse(
            {"ok": False, "error": {"code": "internal_error", "message": str(e)}},
            status_code=500,
        )


@router.put("/{prompt_id}")
async def update_prompt(prompt_id: str, req: UpdatePromptRequest) -> JSONResponse:
    """更新指定提示词的 System/User 核心提示词内容，并重新加载注册表。"""
    try:
        # 1. 获取原文件路径
        if prompt_id not in prompt_registry._sources:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        file_path = Path(prompt_registry._sources[prompt_id])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Prompt file not found on disk")

        # 2. 读取原配置并做局部字段替换与校验
        try:
            current_yaml = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            if not isinstance(current_yaml, dict) or "messages" not in current_yaml:
                raise ValueError("Original file content is not a valid YAML dictionary")

            messages = current_yaml.get("messages", [])
            system_msg = next((m for m in messages if m.get("role") == "system"), None)

            if not system_msg:
                system_msg = {"role": "system", "content": req.system_prompt}
                messages = [system_msg]
            else:
                system_msg["content"] = req.system_prompt
                messages = [system_msg]

            current_yaml["messages"] = messages
            
            # 清空或重置 variables，因为我们不再在 YAML 中需要变量了
            current_yaml["variables"] = {"required": [], "optional": []}
            
            # 校验 Schema 合法性
            PromptSchema.model_validate(current_yaml)
        except Exception as ve:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prompt configuration or validation failed: {ve}",
            ) from ve

        # 3. 写入文件（利用 BlockStyleDumper 格式化排版并防中文转义）
        with file_path.open("w", encoding="utf-8") as f:
            yaml.dump(current_yaml, f, Dumper=BlockStyleDumper, allow_unicode=True, sort_keys=False)

        # 4. 重新加载注册表以使更改立立即生效
        try:
            first_source = Path(next(iter(prompt_registry._sources.values())))
            prompts_dir = first_source.parent.parent

            prompt_registry._frozen = False
            prompt_registry._prompts.clear()
            prompt_registry._sources.clear()
            prompt_registry.load_from_dir(prompts_dir)
            prompt_registry.freeze()
        except Exception as re:
            logger.error("Failed to reload prompt registry after editing: %s", re)
            raise HTTPException(
                status_code=400,
                detail=f"Prompt saved, but registry reload failed: {re}",
            ) from re

        return JSONResponse({"ok": True})

    except HTTPException as he:
        return JSONResponse(
            {"ok": False, "error": {"code": "bad_request", "message": he.detail}},
            status_code=he.status_code,
        )
    except Exception as e:
        logger.error("Failed to update prompt %s: %s", prompt_id, e)
        return JSONResponse(
            {"ok": False, "error": {"code": "internal_error", "message": str(e)}},
            status_code=500,
        )
