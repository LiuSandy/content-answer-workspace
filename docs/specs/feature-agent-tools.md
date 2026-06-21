# Feature: Agent 通用工具集

## 背景

当前对话 Agent（`ConversationGraph`）是纯文本多轮对话，没有工具调用能力。系统提示词里明确写着"你现在不能执行采集、生成回答、发布等系统操作"。

本文档整理需要为 Agent 接入的**通用工具清单**，以及每个工具的安装方式。

---

## 工具清单

### 一、信息获取类

#### `web_search` — 网络搜索
- **作用**：用搜索引擎查询最新信息，返回摘要和链接列表
- **场景**：用户聊某个话题时需要查资料、找数据、了解热点
- **包**：`langchain-community` + `duckduckgo-search`（免费，无需 Key）
- **类**：`langchain_community.tools.DuckDuckGoSearchRun`
- **备选**：`langchain-community` + `tavily-python`，类 `TavilySearchResults`（需要 `TAVILY_API_KEY`，效果更好）
- **状态**：[ ] 待实现

#### `web_fetch` — 读取网页
- **作用**：抓取指定 URL 的正文内容
- **场景**：用户粘贴一篇文章链接，让 Agent 帮忙分析或总结
- **包**：`langchain-community`
- **类**：`langchain_community.tools.requests.tool.RequestsGetTool`
- **状态**：[ ] 待实现

#### `news_search` — 新闻搜索
- **作用**：按关键词搜索最新新闻，返回标题、摘要、来源和发布时间
- **场景**：查某个话题的最新动态、找热点事件背景、了解行业资讯
- **包**：`langchain-community` + `newsapi-python`
- **类**：`langchain_community.tools.NewsAPITool`（需要 `NEWS_API_KEY`，[免费注册](https://newsapi.org)，每月 100 次免费）
- **备选**：`DuckDuckGoSearchRun(backend="news")` 完全免费，无需 Key，精度稍低
- **状态**：[ ] 待实现

---

### 二、计算与执行类

#### `code_interpreter` — Python 代码执行
- **作用**：执行 Python 代码，返回输出结果
- **场景**：数据分析、做复杂计算、处理文本
- **包（本地）**：`langchain-experimental`
- **类**：`langchain_experimental.tools.PythonREPLTool`
- **包（沙箱）**：`e2b-code-interpreter`，需要 `E2B_API_KEY`，生产环境推荐
- **注意**：本地执行有安全风险，仅开发/可信环境使用
- **状态**：[ ] 待实现

#### `calculator` — 数学计算
- **作用**：精确计算数学表达式，避免 LLM 算错
- **场景**：涉及数字、比例、统计的讨论
- **包**：`langchain-community` + `numexpr`
- **类**：`langchain_community.tools.WikipediaQueryRun` ← 不对，用 `@tool` 包装 `numexpr.evaluate()` 更直接
- **状态**：[ ] 待实现

---

### 三、时间与环境类

#### `get_current_datetime` — 获取当前时间
- **作用**：返回当前日期和时间
- **场景**：讨论时效性内容（"最近"、"今年"、"这周"）时 LLM 需要知道当前时间
- **包**：无需安装，用标准库 `datetime` 自定义，5 行代码
- **状态**：[ ] 待实现

```python
from langchain_core.tools import tool
from datetime import datetime

@tool
def get_current_datetime() -> str:
    """返回当前日期和时间。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")
```

---

### 四、记忆类

#### `memory_save` / `memory_search` — 跨会话记忆
- **作用**：把用户偏好、重要信息存入向量库，下次对话可检索
- **场景**：用户说"记住我喜欢用列举式结构写知乎回答"，下次还能生效
- **包**：`langchain-community` + `chromadb` + `langchain-chroma`
- **注意**：引入向量库，复杂度较高，建议最后实现
- **状态**：[ ] 待实现

---

## 安装汇总

```bash
# 搜索 + 网页抓取 + 新闻（核心）
uv add langchain-community duckduckgo-search newsapi-python

# 代码执行（本地开发用）
uv add langchain-experimental

# 代码执行（生产沙箱，可选）
uv add e2b-code-interpreter

# 搜索升级（可选，效果更好）
uv add tavily-python

# 向量记忆（可选，最后做）
uv add chromadb langchain-chroma
```

---

## 接入方式

### 架构变化

当前 `ConversationGraph` 是单节点：

```
START → chat_node → END
```

接入工具后改为 ReAct 模式：

```
START → model_node → [有工具调用?] → tool_node → model_node → ...
                   → [无工具调用?] → END
```

### 关键代码（`conversation.py`）

```python
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.tools.requests.tool import RequestsGetTool

# 1. 组装工具列表（现成包 + 自定义混用）
tools = [
    get_current_datetime,       # 自定义
    DuckDuckGoSearchRun(),      # 直接实例化，不需要写 @tool
    RequestsGetTool(),
]

# 2. 绑定工具到模型
llm_with_tools = llm.bind_tools(tools)

# 3. 改造 graph 结构
graph.add_node("model", model_node)
graph.add_node("tools", ToolNode(tools))
graph.add_conditional_edges("model", tools_condition)
graph.add_edge("tools", "model")
```

---

## 优先级

| 优先级 | 工具 | 包 | 理由 |
|--------|------|----|------|
| P0 | `get_current_datetime` | 无需安装 | 成本极低，验证 ReAct 链路 |
| P1 | `web_search` | `langchain-community` + `duckduckgo-search` | 内容创作最核心需求 |
| P1 | `web_fetch` | `langchain-community` | 与搜索配套 |
| P1 | `news_search` | `langchain-community` + `newsapi-python` | 内容创作需要追热点、查资讯 |
| P2 | `code_interpreter` | `langchain-experimental` | 有价值但需注意安全 |
| P2 | `calculator` | `numexpr` | 覆盖场景较窄 |
| P3 | `memory_save/search` | `chromadb` + `langchain-chroma` | 引入向量库，复杂度高 |

---

## 实施顺序

1. **`get_current_datetime`**：改 graph 结构到 ReAct 模式，零安装成本验证链路
2. **`web_search`** + **`web_fetch`**：`uv add langchain-community duckduckgo-search`，一起上
3. **按需决定** `code_interpreter` 和 `memory`
