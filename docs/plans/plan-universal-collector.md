# Plan: Universal Collector 实施方案

## 设计原则

| 原则 | 体现 |
|------|------|
| 单一职责 | 配置加载、页面获取、HTML 清洗、LLM 提取、字段映射各为独立类 |
| 开闭原则 | 新增平台只加 YAML，新增采集方式只加 Fetcher 实现，不改已有代码 |
| 依赖倒置 | `UniversalCollector` 依赖 `FetcherPort` 和 `ExtractorPort` 接口，不依赖具体实现 |
| 高内聚低耦合 | 采集层不感知 LLM 业务逻辑；LLM 提取层不感知 HTTP 细节 |

---

## 架构分层

```
CollectorFactory（已有，扩展）
        ↓
UniversalCollector              ← 编排层，实现 CollectorPort
    ├── PlatformConfigLoader    ← 配置层，读取 YAML
    ├── FetcherPort             ← 接口
    │     ├── HttpFetcher       ← HTTP 实现（默认）
    │     └── PlaywrightFetcher ← 浏览器实现（可选，JS 重渲染场景）
    ├── HtmlCleaner             ← 工具层，裁剪 HTML
    ├── ExtractorPort           ← 接口
    │     └── LLMExtractor      ← LLM 实现（默认）
    └── QuestionItemMapper      ← 映射层，dict → QuestionItem
```

---

## 接口定义

### FetcherPort

```python
# app/infrastructure/collectors/ports.py
from typing import Protocol

class FetcherPort(Protocol):
    """页面获取器接口：只负责把 URL 变成 HTML 字符串"""

    async def fetch(self, url: str, headers: dict[str, str]) -> str:
        """获取页面 HTML，失败时抛出 FetchError"""
        ...
```

### ExtractorPort

```python
class ExtractorPort(Protocol):
    """内容提取器接口：只负责把 HTML 变成结构化列表"""

    async def extract(
        self, html: str, prompt: str
    ) -> list[dict[str, str]]:
        """按 prompt 描述从 HTML 中提取条目，返回 dict 列表"""
        ...
```

---

## 组件详细设计

### 1. PlatformConfig（值对象）

```python
# app/infrastructure/collectors/platform_config.py
from dataclasses import dataclass, field

@dataclass(frozen=True)   # 不可变，线程安全
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
```

**设计决策**：使用 `frozen=True` 确保配置对象不可变，消除并发场景下的共享状态问题。

### 2. PlatformConfigLoader

```python
# app/infrastructure/collectors/platform_config_loader.py
import yaml
from pathlib import Path
from functools import lru_cache

PLATFORMS_DIR = Path(__file__).parent / "platforms"

class PlatformConfigLoader:
    """
    职责：从 YAML 文件加载并验证平台配置。
    只做 IO + 反序列化，不包含任何业务逻辑。
    """

    @staticmethod
    @lru_cache(maxsize=32)   # 同一进程内配置只读一次
    def load(platform: str) -> PlatformConfig | None:
        path = PLATFORMS_DIR / f"{platform}.yaml"
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return PlatformConfigLoader._parse(raw)

    @staticmethod
    def _parse(raw: dict) -> PlatformConfig:
        auth = raw.get("auth", {})
        pagination = raw.get("pagination", {})
        return PlatformConfig(
            name=raw["name"],
            display_name=raw.get("display_name", raw["name"]),
            auth=AuthConfig(
                method=auth.get("method", "none"),
                env_var=auth.get("env_var"),
            ),
            search_url_template=raw["search"]["url_template"],
            fetcher=raw.get("fetcher", "http"),
            pagination=PaginationConfig(
                type=pagination.get("type", "page"),
                param=pagination.get("param", "page"),
                page_size=pagination.get("page_size", 20),
            ),
            extraction_prompt=raw["extraction_prompt"],
        )
```

### 3. HtmlCleaner（工具类）

```python
# app/infrastructure/collectors/html_cleaner.py
import re
from bs4 import BeautifulSoup

class HtmlCleaner:
    """
    职责：裁剪 HTML，只保留有效文本内容。
    降低传给 LLM 的 token 数量，提升提取准确率。
    """

    _STRIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "head"}
    _MAX_CHARS = 12_000   # LLM context 预算

    def clean(self, raw_html: str) -> str:
        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup.find_all(self._STRIP_TAGS):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # 压缩连续空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[: self._MAX_CHARS]
```

### 4. HttpFetcher

```python
# app/infrastructure/collectors/fetchers/http_fetcher.py
import httpx
from ..ports import FetcherPort

class HttpFetcher:
    """
    职责：使用 httpx 发起 HTTP 请求获取页面。
    负责：超时设置、Cookie 注入、重试。
    不负责：HTML 解析、内容提取。
    """

    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self._cookies = cookies or {}

    async def fetch(self, url: str, headers: dict[str, str]) -> str:
        async with httpx.AsyncClient(
            cookies=self._cookies,
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
```

### 5. LLMExtractor

```python
# app/infrastructure/collectors/extractors/llm_extractor.py
import json
from ..ports import ExtractorPort
from ....infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator

class LLMExtractor:
    """
    职责：调用 LLM 从清洗后的文本中提取结构化条目。
    依赖：DeepSeekAnswerGenerator（复用现有 LLM 客户端）。
    不负责：HTTP 请求、HTML 清洗、字段映射。
    """

    def __init__(self) -> None:
        self._generator = DeepSeekAnswerGenerator()

    async def extract(self, text: str, prompt: str) -> list[dict[str, str]]:
        system = "你只返回 JSON 数组，不要任何额外说明。数组为空时返回 []。"
        user = f"{prompt}\n\n---\n{text}"
        raw = await self._generator.call_raw(system, user)
        return self._parse(raw)

    def _parse(self, raw: str) -> list[dict[str, str]]:
        raw = raw.strip()
        # 兼容 LLM 偶发包裹 markdown code block 的情况
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = raw.rstrip("`").strip()
        try:
            result = json.loads(raw)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []
```

### 6. QuestionItemMapper

```python
# app/infrastructure/collectors/question_item_mapper.py
import uuid
from ....models import QuestionItem

class QuestionItemMapper:
    """
    职责：将 LLM 提取的原始 dict 映射为 QuestionItem。
    职责边界：只做字段对应和缺省值填充，不做业务判断。
    """

    def map(self, raw: dict[str, str], platform: str, topic: str) -> QuestionItem | None:
        title = (raw.get("title") or "").strip()
        url = (raw.get("url") or "").strip()
        if not title or not url:
            return None   # 缺少必填字段，丢弃
        return QuestionItem(
            id=raw.get("id") or str(uuid.uuid5(uuid.NAMESPACE_URL, url)),
            platform=platform,
            title=title,
            url=url,
            excerpt=raw.get("excerpt", ""),
            topic=topic,
            answerCount=0,
        )
```

### 7. UniversalCollector（编排层）

```python
# app/infrastructure/collectors/universal_collector.py
import os
from typing import Sequence
from .platform_config import PlatformConfig
from .platform_config_loader import PlatformConfigLoader
from .html_cleaner import HtmlCleaner
from .fetchers.http_fetcher import HttpFetcher
from .extractors.llm_extractor import LLMExtractor
from .question_item_mapper import QuestionItemMapper
from ...domain.ports import CollectorPort
from ...models import QuestionItem, Topic, WorkflowConfig

class UniversalCollector:
    """
    职责：编排「获取 → 清洗 → 提取 → 映射」流程。
    依赖注入：Fetcher 和 Extractor 通过构造函数注入，便于测试替换。
    不包含：任何平台特定逻辑，平台差异完全由 PlatformConfig 描述。
    """

    platform: str

    def __init__(self, config: PlatformConfig) -> None:
        self._config = config
        self.platform = config.name
        self._fetcher = self._build_fetcher(config)
        self._extractor = LLMExtractor()
        self._cleaner = HtmlCleaner()
        self._mapper = QuestionItemMapper()

    def _build_fetcher(self, config: PlatformConfig):
        cookies = self._load_cookies(config)
        if config.fetcher == "playwright":
            from .fetchers.playwright_fetcher import PlaywrightFetcher
            return PlaywrightFetcher(cookies=cookies)
        return HttpFetcher(cookies=cookies)

    def _load_cookies(self, config: PlatformConfig) -> dict[str, str]:
        if not config.auth.env_var:
            return {}
        cookie_file = os.getenv(config.auth.env_var, "")
        if not cookie_file or not os.path.exists(cookie_file):
            return {}
        # 复用现有 cookie 加载逻辑（与 ZhihuCollector 一致）
        from ...services.zhihu_service import load_cookies_from_file
        return load_cookies_from_file(cookie_file)

    async def collect(
        self, topics: Sequence[Topic], config: WorkflowConfig
    ) -> list[QuestionItem]:
        results: list[QuestionItem] = []
        for topic in topics:
            keywords = topic.expanded_hints or topic.keywords or [topic.name]
            for keyword in keywords:
                url = self._config.search_url_template.format(keyword=keyword)
                try:
                    html = await self._fetcher.fetch(url, self._default_headers(config))
                    text = self._cleaner.clean(html)
                    raw_items = await self._extractor.extract(text, self._config.extraction_prompt)
                    for raw in raw_items:
                        item = self._mapper.map(raw, self.platform, topic.name)
                        if item:
                            results.append(item)
                except Exception:
                    continue   # 单个关键词失败不中断整体采集
        return results

    def _default_headers(self, config: WorkflowConfig) -> dict[str, str]:
        return {"User-Agent": config.user_agent}
```

---

## 文件结构

```
app/infrastructure/collectors/
├── platforms/                         ← 平台配置目录
│   ├── xiaohongshu.yaml
│   └── weibo.yaml
├── fetchers/
│   ├── __init__.py
│   ├── http_fetcher.py                ← HttpFetcher
│   └── playwright_fetcher.py          ← PlaywrightFetcher（可选）
├── extractors/
│   ├── __init__.py
│   └── llm_extractor.py               ← LLMExtractor
├── ports.py                           ← FetcherPort, ExtractorPort（接口）
├── platform_config.py                 ← PlatformConfig 数据类
├── platform_config_loader.py          ← YAML 加载器
├── html_cleaner.py                    ← HTML 裁剪工具
├── question_item_mapper.py            ← dict → QuestionItem 映射
├── universal_collector.py             ← UniversalCollector 编排层
├── factory.py                         ← CollectorFactory（扩展）
└── zhihu_collector.py                 ← 保留不变
```

---

## CollectorFactory 扩展方式

```python
# factory.py 末尾新增 fallback，已有逻辑不改动
from .platform_config_loader import PlatformConfigLoader
from .universal_collector import UniversalCollector

@classmethod
def create(cls, platform, source="auto"):
    # ... 现有逻辑（Zhihu web / official）不变 ...

    # fallback：尝试 YAML 配置
    config = PlatformConfigLoader.load(normalized_platform)
    if config is not None:
        return UniversalCollector(config)

    raise ValueError(f"Unsupported platform: {normalized_platform}")
```

---

## 实施阶段

### Phase 1：基础设施（无外部依赖）
- [ ] 定义 `FetcherPort`、`ExtractorPort` 接口
- [ ] 实现 `PlatformConfig` 数据类
- [ ] 实现 `PlatformConfigLoader`（YAML 加载 + 缓存）
- [ ] 实现 `HtmlCleaner`
- [ ] 实现 `QuestionItemMapper`

### Phase 2：IO 层
- [ ] 实现 `HttpFetcher`
- [ ] 为 `DeepSeekAnswerGenerator` 新增 `call_raw()` 方法（纯 LLM 调用，无业务逻辑）
- [ ] 实现 `LLMExtractor`

### Phase 3：编排层
- [ ] 实现 `UniversalCollector`
- [ ] 扩展 `CollectorFactory` 增加 fallback 逻辑

### Phase 4：第一个平台配置
- [ ] 编写首个非知乎平台的 `platforms/xxx.yaml`
- [ ] 端到端联调验证

### Phase 5：测试
- [ ] `PlatformConfigLoader` 单元测试（YAML 解析正确性）
- [ ] `HtmlCleaner` 单元测试（清洗结果、长度截断）
- [ ] `LLMExtractor` 单元测试（Mock LLM，验证 JSON 解析和容错）
- [ ] `QuestionItemMapper` 单元测试（必填字段缺失时返回 None）
- [ ] `UniversalCollector` 集成测试（Mock Fetcher + Mock Extractor）

---

## 测试策略

每个组件独立可测，关键是**接口隔离**：

```python
# 测试 UniversalCollector 时，注入 Mock Fetcher 和 Mock Extractor
class MockFetcher:
    async def fetch(self, url, headers):
        return "<html>测试页面</html>"

class MockExtractor:
    async def extract(self, text, prompt):
        return [{"title": "测试问题", "url": "https://example.com/q/1"}]

# UniversalCollector 不需要真实网络，完全可测
```

---

## 风险与注意事项

| 风险 | 缓解措施 |
|------|---------|
| LLM 提取不稳定（幻觉/漏提） | `QuestionItemMapper` 做必填字段校验，失败条目静默丢弃 |
| HTML 过长超出 LLM context | `HtmlCleaner` 强制截断至 12000 字符 |
| 平台反爬 | 单个关键词失败不中断整体流程；`PlaywrightFetcher` 作为备选 |
| YAML 配置格式错误 | `PlatformConfigLoader._parse()` 对必填字段做显式 KeyError |
