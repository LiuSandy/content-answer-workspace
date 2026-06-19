from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthConfig:
    method: str           # cookie | oauth | none
    env_var: str | None   # 环境变量名，指向 cookie 文件路径


@dataclass(frozen=True)
class PaginationConfig:
    type: str             # offset | cursor | page
    param: str            # 翻页参数名
    page_size: int


@dataclass(frozen=True)
class PlatformConfig:
    name: str
    display_name: str
    auth: AuthConfig
    search_url_template: str   # 含 {keyword} 占位符
    fetcher: str               # http | playwright
    pagination: PaginationConfig
    extraction_prompt: str
