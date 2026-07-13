"""Prompt Registry 专用错误类型。"""
from __future__ import annotations


class PromptNotFoundError(Exception):
    """请求的 Prompt ID 未注册。"""
    def __init__(self, prompt_id: str):
        super().__init__(f"Prompt not found: '{prompt_id}'")
        self.prompt_id = prompt_id


class PromptVariableMissingError(Exception):
    """渲染时必填变量未提供。"""
    def __init__(self, prompt_id: str, missing: list[str]):
        super().__init__(f"Prompt '{prompt_id}' missing required variables: {missing}")
        self.prompt_id = prompt_id
        self.missing = missing


class PromptRenderError(Exception):
    """Jinja2 渲染失败（通常是未定义变量导致的 UndefinedError）。"""


class PromptDuplicateIdError(Exception):
    """检测到重复 Prompt ID。"""
    def __init__(self, prompt_id: str, file1: str, file2: str):
        super().__init__(f"Duplicate prompt ID '{prompt_id}' in '{file1}' and '{file2}'")
