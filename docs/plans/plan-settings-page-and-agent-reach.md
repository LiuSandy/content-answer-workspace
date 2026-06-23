# Plan: 设置页面 + Agent-Reach 集成实施方案

## 设计原则

| 原则 | 体现 |
|------|------|
| 职责分离 | 密钥存 `.env`，运行时配置存 `.data/settings.json`，Agent-Reach 开关独立存 `.data/agent_reach_config.json` |
| 单一来源 | 后端所有读配置的入口统一走 `SettingsService`，不散落在各模块 |
| 优先级覆盖 | `.env` 始终优先于 JSON 文件（环境变量覆盖 JSON），与现有 `get_workflow_config()` 的 overrides 模式一致 |
| 重启边界清晰 | `ALL_TOOLS` 在进程启动时一次性确定；tool 开关变更后必须重启，设置页提供显式重启按钮 |
| 不破坏现有逻辑 | 现有 `get_workflow_config()` / `get_default_topics()` 保持可用，新配置在其之上叠加 |

---

## 一、存储架构

### 文件分工

```
项目根目录
├── .env                           ← 只存密钥（不纳入 Git）
│     OPENAI_API_KEY=...
│     ZHIHU_COOKIE_FILE=...
│
└── .data/                         ← 运行时写入的数据目录（不纳入 Git）
      ├── settings.json            ← 所有非敏感运行时配置
      ├── agent_reach_config.json  ← Agent-Reach 平台开关 + Groq Key
      └── topics.json              ← 用户自定义主题列表
```

### settings.json 结构

```json
{
  "llm": {
    "baseUrl": "https://open.bigmodel.cn/api/paas/v4/",
    "model": "GLM-4.7"
  },
  "collect": {
    "defaultPlatform": "zhihu",
    "maxPushCount": 10,
    "sortModes": ["latest", "answer_count"],
    "userAgent": "Mozilla/5.0 ...",
    "skipAnswerGeneration": false
  },
  "publish": {
    "testMode": true,
    "officialAccountName": "你的公众号",
    "ctaText": "更多专题内容，欢迎关注公众号：{{OFFICIAL_ACCOUNT_NAME}}"
  },
  "prompts": {
    "systemPrompt": "...",
    "answerStyle": "...",
    "generationPrompt": "..."
  }
}
```

### agent_reach_config.json 结构

```json
{
  "enabledPlatforms": ["bilibili", "github", "rss", "v2ex", "web"],
  "groqApiKey": ""
}
```

### topics.json 结构

```json
[
  {
    "id": "algo",
    "name": "数据结构与算法",
    "keywords": ["数据结构", "算法", "leetcode"],
    "expandedHints": [],
    "answerStyle": "...",
    "systemPrompt": "..."
  }
]
```

### 读取优先级

```
环境变量（.env）
    ↓ 若不存在，则读
.data/settings.json
    ↓ 若不存在，则用
代码中的硬编码默认值（app/core/prompts.py 等）
```

---

## 二、后端：SettingsService

新增 `app/services/settings_service.py`，统一管理所有配置的读写。

### 核心职责

- 读取：合并 `.env` + `settings.json`，返回完整配置对象
- 写入：将变更写入对应文件（密钥写 `.env`，其余写 JSON）
- Agent-Reach 配置：读写 `agent_reach_config.json`
- 主题配置：读写 `topics.json`，不存在时回落到 `get_default_topics()`

### 关键方法签名

```python
# app/services/settings_service.py

class SettingsService:

    def get_all(self) -> dict:
        """合并所有配置来源，返回完整设置（API Key 脱敏）"""

    def update_llm(self, base_url: str, model: str) -> None:
        """更新 LLM 非敏感配置到 settings.json"""

    def update_api_key(self, api_key: str) -> None:
        """写入 OPENAI_API_KEY 到 .env"""

    def update_collect(self, payload: dict) -> None:
        """更新采集默认值到 settings.json"""

    def update_publish(self, payload: dict) -> None:
        """更新发布配置到 settings.json"""

    def update_prompts(self, payload: dict) -> None:
        """更新默认提示词到 settings.json"""

    def get_agent_reach_config(self) -> dict:
        """读取 agent_reach_config.json"""

    def update_agent_reach_config(self, enabled_platforms: list[str]) -> None:
        """写入启用平台列表到 agent_reach_config.json"""

    def configure_groq_key(self, key: str) -> None:
        """调用 agent-reach configure groq-key <key>"""

    def get_topics(self) -> list[dict]:
        """读取 topics.json，不存在时回落到 get_default_topics()"""

    def save_topics(self, topics: list[dict]) -> None:
        """覆盖写入 topics.json"""

    def get_agent_reach_status(self) -> dict:
        """执行 agent-reach doctor --json，返回各平台健康状态"""

    def restart_server(self) -> None:
        """用 os.execv 重启当前进程"""
```

---

## 三、后端：Settings API

新增 `app/api/routes/settings.py`，前缀 `/api/settings`。

### 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 返回全量配置（API Key 脱敏为 `sk-***...***`） |
| POST | `/api/settings/llm` | 更新 LLM 配置（baseUrl / model / apiKey） |
| POST | `/api/settings/collect` | 更新采集默认值 |
| POST | `/api/settings/publish` | 更新发布配置 |
| POST | `/api/settings/prompts` | 更新默认提示词 |
| GET | `/api/settings/agent-reach/status` | 调用 `agent-reach doctor --json`，返回平台状态 |
| POST | `/api/settings/agent-reach/platforms` | 更新启用平台列表 |
| POST | `/api/settings/agent-reach/groq-key` | 配置 Groq API Key |
| GET | `/api/settings/topics` | 返回主题列表 |
| POST | `/api/settings/topics` | 新增主题 |
| PUT | `/api/settings/topics/{topic_id}` | 编辑主题 |
| DELETE | `/api/settings/topics/{topic_id}` | 删除主题 |
| POST | `/api/settings/restart` | 重启后端进程 |
| GET | `/api/health` | 健康检查（已有或新增），供前端轮询重启结果 |

---

## 四、Agent-Reach 配置的四个核心问题

### 1. 开关设计

每个平台一个布尔开关，分两个维度展示在设置页：

```
平台状态（来自 agent-reach doctor）  ×  用户开关（来自 agent_reach_config.json）
         可用                                    已启用   → 正常工作
         可用                                    已禁用   → 不加入 ALL_TOOLS
         不可用（未配置）                         已启用   → 开关置灰 + tooltip 说明原因
         不可用（未安装）                         已禁用   → 开关置灰 + 安装引导
```

开关状态变更后，前端提示用户「点击重启按钮使变更生效」。

### 2. 存储位置

存储在 `.data/agent_reach_config.json`，不放 `.env` 的原因：
- 平台列表是结构化数据，`.env` 的扁平 key-value 不适合存列表
- 该文件不含高敏感信息（Groq Key 为免费 tier，影响面有限）
- 与 `.env` 中的 `OPENAI_API_KEY` 职责分离，避免混杂

### 3. 如何使用（注册到 ALL_TOOLS）

后端启动时，`tools/__init__.py` 读取 `agent_reach_config.json`，
按 `enabledPlatforms` 列表动态决定注册哪些 tool：

```
应用启动
    ↓
读取 .data/agent_reach_config.json
    ↓
enabledPlatforms = ["bilibili", "github", ...]
    ↓
ALL_TOOLS = [
    get_current_datetime,
    web_search,
    web_fetch,
    crawl4ai_fetch,
    news_search,
    code_interpreter,
    calculator,
    # 以下按开关动态追加：
    bilibili_tool,      ← "bilibili" in enabledPlatforms
    github_tool,        ← "github" in enabledPlatforms
    ...
]
    ↓
LangGraph ToolNode 使用 ALL_TOOLS
```

`tools/__init__.py` 变更为：在静态基础列表之后，循环读取配置追加动态 tool。
文件不存在时默认全部关闭（只用静态基础工具），避免启动报错。

### 4. 如何读取

两个读取场景，目的不同：

| 场景 | 时机 | 读取方 | 目的 |
|------|------|--------|------|
| Tool 注册 | 进程启动时（一次） | `tools/__init__.py` | 决定哪些 tool 进入 ALL_TOOLS |
| 设置页展示 | 前端请求时 | `GET /api/settings` | 在 UI 渲染开关的当前状态 |

两者读的是同一个文件，但时机不同。进程启动后修改文件不影响当次运行，需重启才生效。

---

## 五、重启机制

### 后端实现

```
POST /api/settings/restart
    ↓
SettingsService.restart_server()
    ↓
os.execv(sys.executable, [sys.executable] + sys.argv)
    ← 用新进程替换当前进程，端口号不变
```

`os.execv` 是 POSIX 标准调用，替换当前进程镜像，不产生僵尸进程。
FastAPI 的 lifespan 事件会正常触发，已有连接优雅断开。

### 前端轮询流程

```
用户点击「重启后端」
    ↓
POST /api/settings/restart（请求发出后连接断开属正常现象）
    ↓
前端进入 loading 状态
    ↓
每 500ms 发一次 GET /api/health（忽略网络错误）
    ↓
health 返回 200 → 提示「重启成功」→ 重新拉取 GET /api/settings 刷新配置
```

`/api/health` 端点只返回 `{"ok": true}`，无需任何依赖。

### 触发场景

- 变更 Agent-Reach 平台开关后
- 变更 LLM API Key / Base URL / 模型后
- 其他需要重新初始化进程状态的配置变更

视觉设计：按钮固定在设置页顶部 topbar，使用 amber/orange 警示色，
点击后 disabled + loading 旋转，防止重复触发。

---

## 六、Agent-Reach Tool 文件实现

### 各平台 tool 文件

```
app/application/agent/tools/
├── bilibili_tool.py       # bilibili search + video detail（bili-cli）
├── youtube_tool.py        # YouTube subtitle + search（yt-dlp）
├── twitter_tool.py        # tweet read + search（twitter-cli）
├── xiaohongshu_tool.py    # 小红书 search + note（opencli）
├── reddit_tool.py         # Reddit search + post（rdt-cli / opencli）
├── github_tool.py         # GitHub repo search（gh CLI）
├── rss_tool.py            # RSS feed read（feedparser）
└── v2ex_tool.py           # V2EX hot + node（公开 JSON API）
```

### 实现约定

所有平台 tool 遵循统一约定：

```python
# 约定模版（以 bilibili_tool.py 为例）

import subprocess
from langchain_core.tools import tool

_PLATFORM = "bilibili"
_MAX_CHARS = 6000


@tool
def bilibili_search(query: str) -> str:
    """在 B 站搜索视频，返回标题、链接、简介列表。"""
    try:
        result = subprocess.run(
            ["bili", "search", query],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout or result.stderr or "无结果"
        return output[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] CLI 未安装，请在设置页检查 Agent-Reach 状态。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:
        return f"[{_PLATFORM}] 调用失败：{e}"
```

三条约定：
1. 使用同步 `subprocess.run()` + `@tool` 装饰器
2. `FileNotFoundError` 捕获 CLI 未安装场景，返回友好提示，不抛异常
3. 输出统一截断到 6000 字符

### __init__.py 动态注册逻辑

```
读取 .data/agent_reach_config.json
    ↓
_PLATFORM_TOOL_MAP = {
    "bilibili": [bilibili_search, bilibili_video],
    "youtube":  [youtube_fetch],
    "twitter":  [twitter_search, twitter_read],
    ...
}
    ↓
ALL_TOOLS = [...静态基础 tools...]
for platform in enabled_platforms:
    ALL_TOOLS += _PLATFORM_TOOL_MAP.get(platform, [])
```

---

## 七、前端：设置页

### 路由与入口

- 新增路由 `/settings` 到 `App.tsx`
- `AppSidebar` 底部增加「设置」导航项（`Settings` 图标，固定在底部与其他 navItem 分隔）

### 页面布局

```
┌─────────────────────────────────────────────────────┐
│  topbar: [设置]                   [重启后端 ⟳ 按钮]  │
├──────────────┬──────────────────────────────────────┤
│              │                                      │
│  左侧导航    │  右侧内容区                           │
│              │                                      │
│  LLM 配置   │  当前分区的表单                       │
│  Agent-Reach │                                      │
│  主题管理    │                                      │
│  发布配置    │                                      │
│  采集默认值  │                                      │
│  默认提示词  │                                      │
│              │                                      │
└──────────────┴──────────────────────────────────────┘
```

### 各分区组件规划

| 分区 | 组件名 | 关键交互 |
|------|--------|---------|
| LLM 配置 | `LlmSettings` | Base URL 预设下拉 / API Key 脱敏显示 / 保存 |
| Agent-Reach | `AgentReachSettings` | 平台状态列表 / 开关 / 刷新诊断 / 展开配置入口 |
| 主题管理 | `TopicsSettings` | 列表 / 新增 Dialog / 编辑 Dialog / 删除确认 |
| 发布配置 | `PublishSettings` | 测试模式开关 / CTA 实时预览 |
| 采集默认值 | `CollectSettings` | 下拉 + 数字输入 + 高级展开 |
| 默认提示词 | `PromptsSettings` | 复用现有 `PromptField` 组件 |

### Agent-Reach 状态面板展示逻辑

前端合并两个数据源后渲染每一行：

```
GET /api/settings
  → agent_reach_config.enabledPlatforms（用户开关状态）

GET /api/settings/agent-reach/status
  → 各平台健康状态（doctor 诊断结果）

合并 → 每平台展示：
  [平台图标] [平台名] [健康状态徽章] [底层工具名] [启用开关]
             ⚠️ 未配置 时：展开 → 显示配置引导
```

### 数据流

```
前端 SettingsPage
    ↓ 页面挂载
GET /api/settings → 填充所有表单初始值
GET /api/settings/agent-reach/status → 填充平台状态面板
    ↓ 用户修改并点保存
POST /api/settings/{section} → 后端写文件
    ↓ 若涉及需重启的配置（tool 开关 / LLM key）
页面提示「此修改需重启后端生效」，重启按钮高亮
    ↓ 用户点击重启
POST /api/settings/restart
    ↓ 轮询 GET /api/health
    ↓ 恢复后
GET /api/settings 重新拉取，刷新页面状态
```

---

## 八、文件结构

```
后端新增 / 修改
app/
├── services/
│   └── settings_service.py          ← 新增：统一配置读写服务
├── api/routes/
│   └── settings.py                  ← 新增：Settings API 路由
├── application/agent/tools/
│   ├── __init__.py                  ← 修改：动态注册逻辑
│   ├── bilibili_tool.py             ← 新增
│   ├── youtube_tool.py              ← 新增
│   ├── twitter_tool.py              ← 新增
│   ├── xiaohongshu_tool.py          ← 新增
│   ├── reddit_tool.py               ← 新增
│   ├── github_tool.py               ← 新增
│   ├── rss_tool.py                  ← 新增
│   └── v2ex_tool.py                 ← 新增
└── server.py                        ← 修改：注册 settings router

前端新增 / 修改
frontend/src/
├── app/App.tsx                      ← 修改：新增 /settings 路由
├── features/
│   ├── workspace/app-sidebar.tsx    ← 修改：新增设置导航项
│   └── settings/                   ← 新增目录
│       ├── settings-page.tsx        ← 设置页主组件（布局 + 左侧导航）
│       ├── settings-api.ts          ← 所有设置相关 API 调用
│       ├── use-settings.ts          ← TanStack Query hooks
│       ├── llm-settings.tsx
│       ├── agent-reach-settings.tsx
│       ├── topics-settings.tsx
│       ├── publish-settings.tsx
│       ├── collect-settings.tsx
│       └── prompts-settings.tsx

数据目录（运行时生成，不纳入 Git）
.data/
├── settings.json
├── agent_reach_config.json
└── topics.json
```

---

## 九、实施阶段

### Phase 1：存储层与 SettingsService

- [ ] 新增 `.data/` 目录并加入 `.gitignore`
- [ ] 实现 `SettingsService.get_all()` / `update_*()` 系列方法
- [ ] 实现 `get_topics()` / `save_topics()`，回落逻辑接现有 `get_default_topics()`
- [ ] 实现 `get_agent_reach_status()`（subprocess 调用 `agent-reach doctor --json`）
- [ ] 实现 `restart_server()`（`os.execv`）
- [ ] 实现 `GET /api/health` 端点

### Phase 2：Settings API

- [ ] 实现 `GET /api/settings`
- [ ] 实现 `POST /api/settings/llm`
- [ ] 实现 `POST /api/settings/collect` / `publish` / `prompts`
- [ ] 实现 `GET /api/settings/agent-reach/status`
- [ ] 实现 `POST /api/settings/agent-reach/platforms` / `groq-key`
- [ ] 实现 `GET|POST|PUT|DELETE /api/settings/topics`
- [ ] 实现 `POST /api/settings/restart`
- [ ] 在 `server.py` 注册路由

### Phase 3：Agent-Reach Tool 文件

- [ ] 实现 `bilibili_tool.py`（零配置，直接可用）
- [ ] 实现 `github_tool.py`（零配置，直接可用）
- [ ] 实现 `rss_tool.py`（零配置，直接可用）
- [ ] 实现 `v2ex_tool.py`（零配置，直接可用）
- [ ] 实现 `youtube_tool.py`（待修复 PATH 问题）
- [ ] 实现 `twitter_tool.py`（需 Cookie）
- [ ] 实现 `xiaohongshu_tool.py`（需 OpenCLI）
- [ ] 实现 `reddit_tool.py`（需 OpenCLI / rdt-cli）
- [ ] 修改 `tools/__init__.py`：读取配置，动态追加到 `ALL_TOOLS`

### Phase 4：前端设置页基础框架

- [ ] 在 `app-sidebar.tsx` 底部新增设置导航项
- [ ] 在 `App.tsx` 新增 `/settings` 路由
- [ ] 实现 `settings-api.ts`（所有 API 调用函数）
- [ ] 实现 `use-settings.ts`（TanStack Query hooks）
- [ ] 实现 `settings-page.tsx`（两列布局 + 重启按钮 + 轮询逻辑）

### Phase 5：前端各配置分区

- [ ] `llm-settings.tsx`：Base URL 预设 + API Key 脱敏 + 保存
- [ ] `agent-reach-settings.tsx`：平台状态面板 + 开关 + 刷新 + 展开配置引导
- [ ] `topics-settings.tsx`：列表 + 新增/编辑 Dialog + 删除确认
- [ ] `publish-settings.tsx`：测试模式开关 + CTA 实时预览
- [ ] `collect-settings.tsx`：各字段表单
- [ ] `prompts-settings.tsx`：复用 `PromptField` 组件

### Phase 6：联调与测试

- [ ] 各 Settings API 单元测试（模拟文件读写）
- [ ] `SettingsService.restart_server()` 在 dev 环境验证（uvicorn reload 模式下行为）
- [ ] 前端重启轮询流程 E2E 验证
- [ ] Agent-Reach tool 各平台 subprocess 调用验证（已配置渠道）
- [ ] `tools/__init__.py` 动态注册逻辑验证（修改 JSON → 重启 → ALL_TOOLS 变化）

---

## 十、待决策问题

1. ~~**配置热重载**~~ — **已决策**：设置页提供「重启后端」按钮。
2. **platform → tool 粒度** — B 站等平台是合并为一个 tool 还是搜索/详情各一个？建议先合并，需要时再拆。
3. **OpenCLI 环境检测** — 小红书/Reddit 依赖 Chrome 扩展，服务器部署时无法使用，是否在设置页做环境检测并自动切换备用后端？
4. **敏感信息分级** — Groq Key 当前存 `agent_reach_config.json`，若后续平台 Key 增多，统一移入 `.env` 还是新建 `.data/secrets.json`（加密存储）？

---

## 相关文档

- Feature 规划：`docs/specs/feature-agent-reach-integration.md`
- 现有配置层：`app/core/config.py`
- 现有配置 API：`app/api/routes/config.py`（只读，本 plan 在其基础上新增写能力）
- 现有 tools：`app/application/agent/tools/__init__.py`
- 现有前端路由：`frontend/src/app/App.tsx`
- 现有侧边栏：`frontend/src/features/workspace/app-sidebar.tsx`
