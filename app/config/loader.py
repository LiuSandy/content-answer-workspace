"""统一加载 app/config 下的静态配置；单独定义是为了把"硬编码外置"的读取与校验逻辑集中在一处，
让业务模块只依赖类型化的配置对象与提示词读取函数，而不直接碰文件路径与解析细节。"""

from __future__ import annotations

import threading
import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = CONFIG_DIR / "prompts"
SETTINGS_FILE = CONFIG_DIR / "settings.toml"
DEFAULT_TOPICS_FILE = CONFIG_DIR / "default_topics.toml"


class CollectSettings(BaseModel):
    """采集相关运行常量；与平台/分页/上限有关的可调项集中在此。"""

    default_platform: str = "zhihu"
    max_push_count_limit: int = 100
    default_max_push_count: int = 10
    default_sort_modes: list[str] = Field(default_factory=lambda: ["latest", "answer_count"])
    default_page_size: int = 20


class HttpSettings(BaseModel):
    """HTTP 请求与默认 UA；超时和 UA 单独成组，便于统一调整网络行为。"""

    fetch_timeout_seconds: float = 15.0
    client_timeout_seconds: float = 30.0
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )


class PlaywrightSettings(BaseModel):
    """Playwright 渲染等待参数；单独定义以便按反爬强度调整。"""

    goto_timeout_ms: int = 30000
    render_wait_ms: int = 2000


class XiaohongshuSettings(BaseModel):
    """小红书采集节流参数；请求间隔与 cookie 域名集中管理。"""

    request_interval_seconds: float = 1.5
    cookie_domain: str = ".xiaohongshu.com"


class LLMSettings(BaseModel):
    """LLM 非密钥默认值；密钥仍由 .env 提供，这里只放可公开提交的默认模型与地址。"""

    default_model: str = "GLM-4.7"
    default_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"


class Settings(BaseModel):
    """聚合全部运行常量；作为业务层访问配置的唯一类型化入口。"""

    collect: CollectSettings = Field(default_factory=CollectSettings)
    http: HttpSettings = Field(default_factory=HttpSettings)
    playwright: PlaywrightSettings = Field(default_factory=PlaywrightSettings)
    xiaohongshu: XiaohongshuSettings = Field(default_factory=XiaohongshuSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)


_settings_lock = threading.Lock()
_settings: Settings | None = None


def get_settings() -> Settings:
    """返回全局唯一的运行常量对象；用双重检查加锁的单例，避免重复读盘且线程安全。"""

    global _settings
    if _settings is None:
        with _settings_lock:
            if _settings is None:
                _settings = _load_settings()
    return _settings


def _load_settings() -> Settings:
    """读取 settings.toml 并做 Pydantic 校验；文件缺失时回落到模型默认值，保证启动不依赖该文件。"""

    if not SETTINGS_FILE.exists():
        return Settings()
    with SETTINGS_FILE.open("rb") as f:
        raw = tomllib.load(f)
    return Settings.model_validate(raw)




@lru_cache(maxsize=1)
def load_default_topics() -> list[dict]:
    """加载默认主题定义；preset 字段指向 topic_presets，由调用方组装成 Topic。"""

    with DEFAULT_TOPICS_FILE.open("rb") as f:
        data = tomllib.load(f)
    return data.get("topics", [])


def warmup() -> None:
    """启动时一次性预加载并校验所有必需配置；缺文件会在此处尽早暴露而非延迟到请求时。"""

    get_settings()
    load_default_topics()
