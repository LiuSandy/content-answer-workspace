# Feature: Universal Collector — 配置驱动的通用采集器

## 背景与问题

当前每新增一个内容平台，需要：
1. 实现一个新的 `Collector` 类（几百行代码）
2. 编写平台特定的 HTML 解析逻辑（CSS 选择器、字段映射）
3. 在 `CollectorFactory` 中手动注册

HTML 解析逻辑高度耦合平台结构，平台一改版就失效。扩展成本高，维护成本更高。

## 目标

新增平台 = 新建一个 YAML 配置文件，**不写 Python 代码**。

---

## 现有代码（不得破坏）

| 文件 | 现有功能 |
|------|---------|
| `app/domain/ports.py` | `CollectorPort` 接口定义，保留不变 |
| `app/infrastructure/collectors/zhihu_collector.py` | 知乎 Web 爬虫，继续作为实现 |
| `app/infrastructure/collectors/factory.py` | `CollectorFactory`，扩展注册逻辑 |
| `app/application/workflow_service.py` | `WorkflowService.collect()`，调用方不变 |

---

## 设计

### 架构分层

```
WorkflowService.collect()
        ↓
CollectorFactory.create(platform, source)
        ↓
  ┌─────────────────────────────────┐
  │  已有实现（保留）                │
  │  ZhihuCollector                 │
  └─────────────────────────────────┘
        ↓ 新平台走这里
  ┌─────────────────────────────────┐
  │  UniversalCollector（新增）      │
  │  读取 PlatformConfig（YAML）     │
  │  HTTP 请求 → 原始 HTML           │
  │  LLM 按 Prompt 提取结构化数据    │
  │  返回 QuestionItem[]            │
  └─────────────────────────────────┘
```

### 平台配置文件（YAML）

路径：`app/infrastructure/collectors/platforms/{platform}.yaml`

```yaml
# app/infrastructure/collectors/platforms/xiaohongshu.yaml
name: xiaohongshu
display_name: 小红书
auth:
  method: cookie                          # cookie | oauth | none
  env_var: XIAOHONGSHU_COOKIE_FILE        # 存放 cookie 文件路径的环境变量名
search:
  url_template: "https://www.xiaohongshu.com/search_result?keyword={keyword}"
  method: GET
  pagination:
    type: offset                          # offset | cursor | page
    param: page
    page_size: 20
extraction_prompt: |
  从以下 HTML 中提取所有笔记/问题条目，返回 JSON 数组，每条包含：
  - id: 内容唯一标识（从 URL 或 data-id 属性提取）
  - title: 标题
  - url: 完整链接
  - excerpt: 摘要（如有）
  - heat: 热度/点赞数（如有，返回字符串）
  只返回 JSON，不要任何说明文字。
```

### 核心组件

**`PlatformConfig`（数据类）**

```python
# app/infrastructure/collectors/platform_config.py
@dataclass
class PlatformConfig:
    name: str
    display_name: str
    auth_method: str           # cookie | oauth | none
    auth_env_var: str | None
    search_url_template: str
    extraction_prompt: str
    pagination_type: str       # offset | cursor | page
```

**`UniversalCollector`**

```python
# app/infrastructure/collectors/universal_collector.py
class UniversalCollector:
    platform: str

    def __init__(self, config: PlatformConfig) -> None: ...

    async def collect(
        self, topics: Sequence[Topic], config: WorkflowConfig
    ) -> list[QuestionItem]:
        # 1. 读取 auth cookie（从 config.auth_env_var 指定的文件）
        # 2. 按 topic.expanded_hints 逐个关键词构造搜索 URL
        # 3. httpx 请求（或 Playwright 渲染，由 config 决定）
        # 4. 调用 LLMExtractor.extract(html, extraction_prompt)
        # 5. 将结果映射为 QuestionItem
        ...
```

**`LLMExtractor`**

```python
# app/infrastructure/collectors/llm_extractor.py
class LLMExtractor:
    async def extract(
        self, html: str, prompt: str
    ) -> list[dict[str, Any]]:
        # 裁剪 HTML（只保留 body，去掉 script/style）
        # 调用 LLM：prompt + cleaned_html → JSON
        # 解析返回的 JSON 数组
        ...
```

### CollectorFactory 扩展

```python
# 现有逻辑不变，末尾增加 fallback：
@classmethod
def create(cls, platform: str | None, source: str = "auto") -> CollectorPort:
    # ... 现有逻辑（zhihu web / official）...

    # 新增：尝试加载平台配置文件
    config = PlatformConfigLoader.load(normalized_platform)
    if config is not None:
        return UniversalCollector(config)

    raise ValueError(f"Unsupported platform: {normalized_platform}")
```

---

## 数据模型变更

无需修改 `QuestionItem`、`Topic`、`WorkflowConfig`。

`UniversalCollector` 提取后统一映射到现有 `QuestionItem`，`platform` 字段设为 YAML 中的 `name`。

---

## 环境变量约定

新平台的 Cookie 路径通过 YAML 中 `auth.env_var` 指定的环境变量名读取，格式与现有 `ZHIHU_COOKIE_FILE` 一致。

---

## 不受影响的现有功能

- 知乎 web 爬虫（`ZhihuCollector`）：逻辑完全保留
- `WorkflowService.collect()`：调用签名不变
- 前端所有采集相关 API：`/api/workflow/collect` 接口不变

---

## 实现顺序

1. `PlatformConfig` 数据类 + YAML loader
2. `LLMExtractor`（复用现有 DeepSeek 客户端）
3. `UniversalCollector`
4. `CollectorFactory` 增加 fallback 逻辑
5. 编写第一个非知乎平台的 YAML 配置验证

---

## 依赖

无前置 Feature 依赖，可独立实现。
