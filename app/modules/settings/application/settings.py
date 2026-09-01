"""统一管理所有运行时配置的读写；单独定义是为了将配置持久化逻辑与业务逻辑完全隔离。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.platform.config.loader import get_settings
from app.platform.config.llm import load_llm_runtime_config
from app.platform.config.runtime import (
    ENV_PATH,
    ROOT_DIR,
    get_default_topics,
    is_truthy,
    load_env_file,
)
from app.modules.acquisition.domain.workflow import Topic

DATA_DIR = ROOT_DIR / ".data"
SETTINGS_FILE = DATA_DIR / "settings.json"
AGENT_REACH_CONFIG_FILE = DATA_DIR / "agent_reach_config.json"
TOPICS_FILE = DATA_DIR / "topics.json"

_AGENT_REACH_PLATFORMS = ["bilibili", "youtube", "twitter", "xiaohongshu", "reddit", "github", "rss", "v2ex", "web"]
_TWITTER_ENV_KEYS = ("TWITTER_AUTH_TOKEN", "TWITTER_CT0")


def _read_json(path: Path) -> dict[str, Any]:
    """安全读取 JSON 文件；不存在时返回空字典，避免调用方判断文件是否存在。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    """原子写入 JSON 文件；先确保目录存在，再格式化写入，避免文件损坏。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _mask_key(key: str) -> str:
    """将 API Key 脱敏显示；保留前后各 4 位，中间替换为星号。"""
    if not key or len(key) < 12:
        return "***"
    return f"{key[:4]}***{key[-4:]}"


def _read_env_value(name: str) -> str:
    """从 .env 文件读取指定变量的原始值；用于脱敏展示，不依赖 os.environ。"""
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line[len(name) + 1:].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return ""


def _write_env_value(name: str, value: str) -> None:
    """写入或更新 .env 文件中的指定变量；已存在则更新，不存在则追加。"""
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    found = False
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        pass

    new_lines: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{name}="):
            new_lines.append(f'{name}={value}')
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f'{name}={value}')

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


class SettingsService:
    """统一配置读写服务；所有配置的持久化入口都在此类中，避免散落在各模块。"""

    def get_all(self) -> dict[str, Any]:
        """合并所有配置来源，返回完整设置（API Key 脱敏）。"""
        load_env_file()
        settings = _read_json(SETTINGS_FILE)

        collect = settings.get("collect", {})
        publish = settings.get("publish", {})
        prompts = settings.get("prompts", {})

        llm_config = load_llm_runtime_config()
        default_binding = llm_config.default
        default_provider = llm_config.providers[default_binding.provider]
        default_model = default_binding.model or default_provider.default_model

        return {
            "llm": {
                "baseUrl": default_provider.base_url,
                "model": default_model,
                "apiKey": _mask_key(default_provider.api_key),
            },
            "collect": {
                "defaultPlatform": collect.get("defaultPlatform")
                or os.getenv("DEFAULT_PLATFORM", get_settings().collect.default_platform),
                "maxPushCount": collect.get("maxPushCount")
                or int(os.getenv("MAX_PUSH_COUNT", str(get_settings().collect.default_max_push_count))),
                "sortModes": collect.get("sortModes") or list(get_settings().collect.default_sort_modes),
                "userAgent": collect.get("userAgent") or os.getenv("HTTP_USER_AGENT", get_settings().http.user_agent),
                "skipAnswerGeneration": collect.get("skipAnswerGeneration", False),
            },
            "publish": {
                "testMode": publish.get("testMode", is_truthy(os.getenv("TEST_MODE", "true"))),
                "officialAccountName": publish.get("officialAccountName") or os.getenv("OFFICIAL_ACCOUNT_NAME", "你的公众号"),
                "ctaText": publish.get("ctaText") or os.getenv(
                    "OFFICIAL_ACCOUNT_CTA", "更多专题内容，欢迎关注公众号：{{OFFICIAL_ACCOUNT_NAME}}"
                ),
            },
            "agentReach": self.get_agent_reach_config(),
        }

    def update_llm(self, base_url: str, model: str) -> None:
        """更新 LLM 非敏感配置到 settings.json。"""
        data = _read_json(SETTINGS_FILE)
        data["llm"] = {**data.get("llm", {}), "baseUrl": base_url, "model": model}
        _write_json(SETTINGS_FILE, data)

    def update_api_key(self, api_key: str) -> None:
        """写入 OPENAI_API_KEY 到 .env 文件。"""
        _write_env_value("OPENAI_API_KEY", api_key)

    def update_collect(self, payload: dict[str, Any]) -> None:
        """更新采集默认值到 settings.json。"""
        data = _read_json(SETTINGS_FILE)
        data["collect"] = {**data.get("collect", {}), **payload}
        _write_json(SETTINGS_FILE, data)

    def update_publish(self, payload: dict[str, Any]) -> None:
        """更新发布配置到 settings.json。"""
        data = _read_json(SETTINGS_FILE)
        data["publish"] = {**data.get("publish", {}), **payload}
        _write_json(SETTINGS_FILE, data)


    def get_agent_reach_config(self) -> dict[str, Any]:
        """读取 agent_reach_config.json；文件不存在时返回空平台列表。"""
        data = _read_json(AGENT_REACH_CONFIG_FILE)
        return {
            "enabledPlatforms": data.get("enabledPlatforms", []),
            "groqApiKey": _mask_key(data.get("groqApiKey", "")),
        }

    def update_agent_reach_config(self, enabled_platforms: list[str]) -> None:
        """写入启用平台列表到 agent_reach_config.json。"""
        data = _read_json(AGENT_REACH_CONFIG_FILE)
        valid_platforms = [p for p in enabled_platforms if p in _AGENT_REACH_PLATFORMS]
        data["enabledPlatforms"] = valid_platforms
        _write_json(AGENT_REACH_CONFIG_FILE, data)

    def configure_groq_key(self, key: str) -> None:
        """将 Groq API Key 写入 agent_reach_config.json。"""
        data = _read_json(AGENT_REACH_CONFIG_FILE)
        data["groqApiKey"] = key
        _write_json(AGENT_REACH_CONFIG_FILE, data)

    def get_topics(self) -> list[dict[str, Any]]:
        """读取 topics.json；不存在时回落到 get_default_topics()。"""
        if TOPICS_FILE.exists():
            try:
                raw = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, list) and raw:
                    return raw
            except (json.JSONDecodeError, ValueError):
                pass
        return [t.model_dump(by_alias=True) for t in get_default_topics()]

    def save_topics(self, topics: list[dict[str, Any]]) -> None:
        """覆盖写入 topics.json。"""
        _write_json(TOPICS_FILE, topics)

    def get_agent_reach_status(self) -> dict[str, Any]:
        """执行 agent-reach doctor --json，返回各平台健康状态；CLI 不存在时返回错误信息。"""
        try:
            result = subprocess.run(
                ["agent-reach", "doctor", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout.strip() or result.stderr.strip()
            try:
                return {"ok": True, "data": json.loads(output)}
            except json.JSONDecodeError:
                return {"ok": True, "data": {"raw": output}}
        except FileNotFoundError:
            return {
                "ok": False,
                "error": "agent-reach CLI 未安装，请参考文档安装后重试。",
                "platforms": {},
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "agent-reach doctor 超时（30s）。"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def get_twitter_auth(self) -> dict[str, str]:
        """读取 Twitter 认证字段（脱敏）；twitter-cli 通过这两个环境变量认证。"""
        return {
            "authToken": _mask_key(_read_env_value("TWITTER_AUTH_TOKEN")),
            "ct0": _mask_key(_read_env_value("TWITTER_CT0")),
        }

    def save_twitter_auth(self, auth_token: str, ct0: str) -> None:
        """将 TWITTER_AUTH_TOKEN 和 TWITTER_CT0 写入 .env；twitter-cli 启动时读取。"""
        if auth_token:
            _write_env_value("TWITTER_AUTH_TOKEN", auth_token)
        if ct0:
            _write_env_value("TWITTER_CT0", ct0)

    def get_twitter_configured(self) -> bool:
        """判断 Twitter 是否已配置认证信息。"""
        return bool(_read_env_value("TWITTER_AUTH_TOKEN") and _read_env_value("TWITTER_CT0"))

    def restart_server(self) -> None:
        """用 os.execv 替换当前进程以重启后端；端口号不变，lifespan 事件正常触发。
        以 -m 方式启动时必须重建 -m 参数，否则直接用文件路径会触发相对导入错误。"""
        import __main__
        spec = getattr(__main__, "__spec__", None)
        if spec is not None and spec.name:
            os.execv(sys.executable, [sys.executable, "-m", spec.name])
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)
