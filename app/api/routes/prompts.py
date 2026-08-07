from __future__ import annotations

import logging
from pathlib import Path
import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...prompts.errors import PromptNotFoundError
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


def _resolve_prompt_file(prompt_id: str) -> Path:
    """把 prompt_id 解析为磁盘上的源文件；不存在时抛 404。

    单独抽出是因为 GET 与 PUT 共用同一套解析与存在性校验。
    """
    try:
        file_path = prompt_registry.get_source_path(prompt_id)
    except PromptNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Prompt file not found on disk")
    return file_path


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: str) -> JSONResponse:
    """获取指定提示词的可编辑内容。

    支持两种 YAML 形态：
    - messages 型（如 writing.answer_generate）：返回 system 消息内容
    - content 片段型（如 platform.zhihu 平台包）：返回 content 字段
    """
    try:
        file_path = _resolve_prompt_file(prompt_id)
        parsed = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Invalid prompt YAML structure")

        if "messages" in parsed:
            messages = parsed.get("messages", [])
            system_msg = next((m for m in messages if m.get("role") == "system"), None)
            user_msg = next((m for m in messages if m.get("role") == "user"), None)
            if not system_msg:
                raise ValueError("Prompt template must contain a system message")
            system_content = system_msg.get("content", "")
            user_content = user_msg.get("content", "") if user_msg else ""
            kind = "messages"
        elif "content" in parsed:
            system_content = parsed.get("content", "")
            user_content = ""
            kind = "fragment"
        else:
            raise ValueError("Prompt YAML must contain 'messages' or 'content'")

        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "id": prompt_id,
                    "kind": kind,
                    "systemPrompt": system_content,
                    "userPrompt": user_content,
                    "filePath": str(file_path),
                },
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to read prompt %s: %s", prompt_id, e)
        return JSONResponse(
            {"ok": False, "error": {"code": "internal_error", "message": "读取提示词失败"}},
            status_code=500,
        )


@router.put("/{prompt_id}")
async def update_prompt(prompt_id: str, req: UpdatePromptRequest) -> JSONResponse:
    """更新指定提示词内容并重新加载注册表。

    messages 型更新 system 消息；content 片段型（平台包等）更新 content 字段。
    """
    try:
        file_path = _resolve_prompt_file(prompt_id)

        # 读取原配置并做局部字段替换与校验
        try:
            current_yaml = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            if not isinstance(current_yaml, dict):
                raise ValueError("Original file content is not a valid YAML dictionary")

            if "messages" in current_yaml:
                messages = current_yaml.get("messages", [])
                system_msg = next((m for m in messages if m.get("role") == "system"), None)
                if not system_msg:
                    system_msg = {"role": "system", "content": req.system_prompt}
                    messages = [system_msg] + [m for m in messages if m.get("role") != "system"]
                else:
                    system_msg["content"] = req.system_prompt
                # 保留既有 user message；请求携带非空 userPrompt 时更新它，否则保持不变
                user_msg = next((m for m in messages if m.get("role") == "user"), None)
                new_user_prompt = (req.user_prompt or "").strip() if req.user_prompt else None
                if user_msg is not None:
                    if new_user_prompt:
                        user_msg["content"] = new_user_prompt
                elif new_user_prompt:
                    messages.append({"role": "user", "content": new_user_prompt})
                # 按角色分组：system 在前，user 在后，其余角色保持原顺序
                system_msgs = [m for m in messages if m.get("role") == "system"]
                user_msgs = [m for m in messages if m.get("role") == "user"]
                other_msgs = [m for m in messages if m.get("role") not in ("system", "user")]
                current_yaml["messages"] = system_msgs + user_msgs + other_msgs
                # 保留原始 variables 结构，编辑器只改消息内容，不破坏模板变量
            elif "content" in current_yaml:
                current_yaml["content"] = req.system_prompt
            else:
                raise ValueError("Prompt YAML must contain 'messages' or 'content'")

            # 校验 Schema 合法性
            PromptSchema.model_validate(current_yaml)
        except Exception as ve:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prompt configuration or validation failed: {ve}",
            ) from ve

        # 写入文件（利用 BlockStyleDumper 格式化排版并防中文转义）
        with file_path.open("w", encoding="utf-8") as f:
            yaml.dump(current_yaml, f, Dumper=BlockStyleDumper, allow_unicode=True, sort_keys=False)

        # 重新加载注册表以使更改立即生效
        try:
            prompt_registry.reload()
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
            {"ok": False, "error": {"code": "internal_error", "message": "更新提示词失败"}},
            status_code=500,
        )
