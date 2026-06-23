# Feature: Agent-Reach 集成 + 设置页面

## 背景

Agent-Reach 是一个开源 CLI 工具（零 API 费用），为 AI Agent 提供对 13 个互联网平台的读取/搜索能力。
本项目已将其安装（v1.5.0），底层工具（bili-cli、twitter-cli、yt-dlp、OpenCLI 等）均已就位。

本 feature 拆分为两个关联目标：
1. 新增**设置页面** (`/settings`)，统一管理所有在线配置
2. 将 Agent-Reach 平台封装为 LangChain `@tool`，注册到 `ALL_TOOLS`，供对话 Agent 调用

---

## 一、设置页面规划

### 入口

在左侧 `AppSidebar` 底部固定一个 **设置** 导航项（齿轮图标），路由 `/settings`，与其他页面并列。
设置页本身使用左侧分类导航 + 右侧内容区的两列布局。

### 配置分区

#### 1. LLM 配置

> 当前状态：全部硬编码在 `.env`，前端无法感知也无法修改。

涵盖字段（来自 `app/core/config.py`）：

| 字段 | 环境变量 | 说明 |
|------|---------|------|
| API Key | `OPENAI_API_KEY` | 必填，敏感字段，保存后脱敏显示 |
| Base URL | `OPENAI_BASE_URL` | 默认智谱 AI，支持手动输入或预设切换（OpenAI / 智谱 / 自定义） |
| 模型名称 | `OPENAI_MODEL` | 如 `GLM-4.7`、`gpt-4o` |

交互：
- 保存后立即生效（重写 `.env`），无需重启后端
- Base URL 提供常用预设下拉（OpenAI、智谱、DeepSeek），选中后自动填充 URL 和推荐模型名

#### 2. Agent-Reach 平台配置

> 用户明确需求：在线配置 Agent-Reach 的所有 tool。

**状态面板**（主要区域）：
- 展示所有 13 个平台的当前状态，数据来自后端调用 `agent-reach doctor --json`
- 每个平台一行：平台图标 + 名称 + 状态徽章（✅ 可用 / ⚠️ 需配置 / ❌ 未安装）+ 当前使用的底层工具
- 顶部「刷新状态」按钮，点击重新运行诊断

| 平台 | 零配置可用 | 需要额外配置 |
|------|-----------|------------|
| 任意网页 | ✅ | — |
| GitHub | ✅ | — |
| V2EX | ✅ | — |
| RSS/Atom | ✅ | — |
| 全网搜索 | ✅ | — |
| B站 | ✅（搜索） | bili-cli 完整安装 |
| YouTube | ⚠️ | yt-dlp PATH 问题待修复 |
| Twitter/X | ⚠️ | 需登录浏览器导入 Cookie |
| Reddit | ⚠️ | OpenCLI Chrome 扩展 + 登录 |
| 小红书 | ⚠️ | OpenCLI Chrome 扩展 + 登录 |
| 小宇宙播客 | ⚠️ | Groq 免费 API Key |
| 雪球 | ⚠️ | 浏览器 Cookie |
| LinkedIn | ⚠️ | OpenCLI Chrome 扩展 |

**配置入口**（每个 ⚠️ 平台展开后显示）：

- **Groq API Key**（小宇宙）：输入框 + 保存，调用 `agent-reach configure groq-key xxx`
- **OpenCLI 安装引导**（小红书/Reddit/LinkedIn）：显示扩展安装链接，带「已安装，重新检测」按钮
- **Cookie 导入状态**（Twitter/雪球）：显示最近导入时间 + 「重新导入」按钮（触发 `agent-reach install --channels=twitter`）

**Tool 注册开关**：
- 每个平台一个开关，控制该平台的 `@tool` 是否加入 `ALL_TOOLS`
- 未通过诊断的平台开关置灰，带 tooltip 说明原因
- 配置持久化到后端（写入 `.env` 或独立 JSON 配置文件）

#### 3. 主题管理

> 当前状态：主题硬编码在 `app/core/config.py` 的 `get_default_topics()`，前端无法增删改。

功能：
- 显示当前所有预设主题列表
- 新增主题：填写名称 / 关键词 / 主题提示词 / 回答风格
- 编辑主题：修改现有主题的上述字段
- 删除主题：二次确认后删除
- 主题数据持久化到独立 JSON 文件（如 `.data/topics.json`），后端优先读取该文件，不存在则用默认值

#### 4. 发布配置

> 当前状态：公众号 CTA 信息在 `.env`，测试模式影响生成回答的尾部追加。

字段：

| 字段 | 环境变量 | 说明 |
|------|---------|------|
| 测试模式 | `TEST_MODE` | 开启时不追加 CTA，开关控件 |
| 公众号名称 | `OFFICIAL_ACCOUNT_NAME` | 替换 CTA 中的占位符 |
| CTA 文案模板 | `OFFICIAL_ACCOUNT_CTA` | Textarea，含 `{{OFFICIAL_ACCOUNT_NAME}}` 占位符 |

交互：
- 实时预览拼接后的 CTA 文案

#### 5. 采集默认值

> 当前状态：各参数分散在 `.env`，每次采集可覆盖，但无全局默认入口。

字段：

| 字段 | 环境变量 | 说明 |
|------|---------|------|
| 默认平台 | `DEFAULT_PLATFORM` | 下拉选择 |
| 单次采集上限 | `MAX_PUSH_COUNT` | 数字输入，最大 100 |
| 排序模式 | `SORT_MODES` | 多选或逗号分隔输入 |
| User-Agent | `HTTP_USER_AGENT` | Textarea，高级选项 |
| 跳过回答生成 | `SKIP_ANSWER_GENERATION` | 开关 |

#### 6. 默认提示词

> 当前状态：默认提示词在 `app/core/prompts.py` 硬编码，运行时可在各页面左侧面板覆盖，但无持久化的全局默认入口。

字段：
- 全局系统提示词（`SYSTEM_PROMPT`）
- 全局回答风格（`ANSWER_STYLE`）
- 全局生成规则（`GENERATION_PROMPT`）

每个字段使用带「全屏」按钮的 Textarea（复用现有 `PromptField` 组件）。

---

## 二、后端改造需求

### 新增设置读写 API

| 端点 | 方法 | 作用 |
|------|------|------|
| `/api/settings` | GET | 返回所有可配置项的当前值（脱敏 API Key） |
| `/api/settings` | POST | 接收并持久化配置变更（写 `.env` 或 JSON） |
| `/api/settings/agent-reach/status` | GET | 调用 `agent-reach doctor --json`，返回各平台状态 |
| `/api/settings/agent-reach/configure` | POST | 调用 `agent-reach configure <key> <value>` |
| `/api/settings/topics` | GET | 返回主题列表 |
| `/api/settings/topics` | POST/PUT/DELETE | 主题的增删改，持久化到 `.data/topics.json` |
| `/api/settings/restart` | POST | 重启后端进程 |

### Agent-Reach Tool 注册机制

- 后端维护一份 `agent_reach_enabled_platforms` 配置（JSON 或 `.env` 中的 key）
- 应用启动时根据该配置动态决定哪些平台 tool 加入 `ALL_TOOLS`
- 设置页切换开关 → 调用设置 API → 后端更新配置 → **点击重启按钮使变更生效**

### 重启按钮

设置页顶部固定一个「重启后端」按钮，行为：
1. 前端调用 `POST /api/settings/restart`
2. 后端收到请求后用 `os.execv` 重新启动自身进程
3. 前端进入等待状态（轮询 `GET /api/health`），恢复后提示「重启成功」
4. 页面自动刷新配置，反映最新 tool 注册状态

触发场景：
- 切换 Agent-Reach 平台 tool 的启用/禁用开关后
- 修改 LLM 配置（API Key / Base URL / 模型）后
- 任何需要重新初始化后端状态的配置变更后

视觉设计：按钮使用警示色（amber/orange），点击后显示 loading 旋转，避免重复点击。

---

## 三、Agent-Reach Tool 集成规划

### 集成架构

```
agent-reach 底层 CLI（twitter-cli / bili-cli / yt-dlp / rdt-cli / opencli ...）
        ↓ subprocess.run()
@tool 封装（每平台一个文件，app/application/agent/tools/）
        ↓ 按配置动态注册
ALL_TOOLS → LangGraph ToolNode → 对话 Agent
```

### 计划文件

```
app/application/agent/tools/
├── bilibili_tool.py       # B站搜索 + 视频详情（bili-cli）
├── youtube_tool.py        # YouTube 字幕 + 搜索（yt-dlp）
├── twitter_tool.py        # 推文读取 + 搜索（twitter-cli）
├── xiaohongshu_tool.py    # 小红书搜索 + 笔记（opencli）
├── reddit_tool.py         # Reddit 搜索 + 帖子（rdt-cli / opencli）
├── github_tool.py         # GitHub 仓库搜索（gh CLI）
├── rss_tool.py            # RSS 订阅源读取（feedparser）
└── v2ex_tool.py           # V2EX 热榜 + 节点（公开 API）
```

每个 tool 文件：
- 使用同步 `subprocess.run()` + `@tool` 装饰器
- CLI 未安装/未登录时返回友好错误消息，不抛异常
- 输出截断统一为 6000 字符（当前 `web_fetch` 是 5000）

### 待决策问题

1. ~~**配置热重载**~~ — **已决策**：设置页提供「重启后端」按钮，点击后后端重启、前端等待恢复。
2. **platform → tool 的粒度** — B站是做一个 `bilibili_tool`（搜索+详情），还是两个独立 tool？
3. **OpenCLI 桌面依赖** — 小红书/Reddit 依赖 Chrome 浏览器，设置页是否做环境检测，在服务器模式下自动切换到备用后端？
4. **敏感信息存储** — API Key 写入 `.env` 还是系统 Keychain？

---

## 四、安装现状

截至安装时（2026-06-23，agent-reach v1.5.0）：

| 状态 | 渠道 | 当前后端 |
|------|------|---------|
| ✅ 可用 | GitHub | gh CLI |
| ✅ 可用 | V2EX | 公开 JSON API |
| ✅ 可用 | RSS/Atom | feedparser |
| ✅ 可用 | 全网搜索 | Exa via mcporter |
| ✅ 可用 | 任意网页 | Jina Reader |
| ✅ 可用（搜索） | B站 | B站搜索 API（bili-cli 已装待验证） |
| ❌ 待修复 | YouTube | yt-dlp PATH 问题 |
| ⚠️ 需登录 | Twitter/X | twitter-cli 已装 |
| ⚠️ 需 Chrome 扩展 | Reddit | OpenCLI 已装 |
| ⚠️ 需 Chrome 扩展 | 小红书 | OpenCLI 已装 |
| ⚠️ 需 Groq Key | 小宇宙播客 | transcribe.sh 已装 |
| ⚠️ 需 Cookie | 雪球 | — |
| ⚠️ 需 Chrome 扩展 | LinkedIn | OpenCLI 已装 |

手动配置步骤：
- OpenCLI Chrome 扩展：https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
- Groq API Key（免费）：https://console.groq.com → `agent-reach configure groq-key gsk_xxxxx`

---

## 五、相关资源

- Agent-Reach Repo: https://github.com/Panniantong/Agent-Reach
- 现有 tools 目录: `app/application/agent/tools/`
- 现有配置层: `app/core/config.py`
- 现有配置 API: `app/api/routes/config.py`（当前只读，需扩展为读写）
- 现有前端路由: `frontend/src/app/App.tsx`
- 现有侧边栏: `frontend/src/features/workspace/app-sidebar.tsx`
