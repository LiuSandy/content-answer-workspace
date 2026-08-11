# Feature: 小红书平台接入 — 笔记仿写 + 评论区问答双模式采集

## 背景与问题

当前采集层只支持知乎，走"接口逆向 + 签名"或"官方 API"两条路（见 `feature-universal-collector.md` 中的 `UniversalCollector`，假设新平台用简单 HTTP 请求即可拿到结构化内容）。这个假设在小红书上不成立：

- 小红书 web 端搜索和笔记详情页强制依赖登录态，未登录时搜索结果被严重裁剪、正文和评论区会被"登录查看更多"浮层挡住。
- 小红书的请求签名（x-s/x-t）是动态 JS 算法，逆向成本高、容易随版本更新失效，不适合直接走 HTTP 接口逆向。

同时，小红书没有知乎那种"问题"语义，主要内容形式是图文笔记（笔记标题 + 正文 + 标签 + 评论区）。业务上需要两种不同的采集产出，分别对应两种不同的下游生成逻辑：

1. **笔记仿写素材**：采集笔记本身（标题+正文），AI 参考其选题角度和写作风格创作全新笔记。
2. **评论区问答**：采集笔记评论区里用户提出的疑问，复用知乎现有的"问题 → 回答"生成逻辑。

## 目标

- 新增 `xiaohongshu` 作为可选采集平台，走独立的 `XiaohongshuCollector`，不复用 `UniversalCollector` 的 YAML + 单次 HTTP fetch 路径。
- 采集层支持 cookie 登录态注入 + Playwright 渲染，规避签名逆向。
- 支持两种采集模式（`content_mode`: `answer` / `imitate`），分别产出"评论区问题"和"笔记仿写素材"。
- 下游生成阶段（`DeepSeekAnswerGenerator`）根据 `content_mode` 选择对应提示词模板。
- 不破坏知乎现有采集与生成逻辑；`content_mode` 默认值保持知乎现状不变。
- 图片生成（`images`/`imagePrompts` 字段的实际填充）明确不在本次范围内，字段保留现状，留给后续迭代。

## 现有代码（不得破坏）

| 文件 | 现有功能 |
|------|---------|
| `app/domain/ports.py` | `CollectorPort` 接口定义，保留不变 |
| `app/infrastructure/collectors/zhihu_collector.py` | 知乎网页采集逻辑，继续作为实现，不修改 |
| `app/infrastructure/collectors/factory.py` | `CollectorFactory`，新增 `xiaohongshu` 注册，现有逻辑不变 |
| `app/infrastructure/collectors/universal_collector.py` | 通用采集器，本次不复用其编排逻辑，但复用其下属的 fetcher 抽象 |
| `app/application/workflow_service.py` | `WorkflowService.collect()`，调用签名不变 |
| `app/infrastructure/llm/deepseek_client.py` | `DeepSeekAnswerGenerator`，新增 `content_mode` 分支，现有"回答"逻辑不变 |
| `app/models.py` | `QuestionItem` / `WorkflowConfig`，新增字段，现有字段不变 |

## 设计

### 为什么不用 UniversalCollector（与 feature-universal-collector.md 的差异说明）

`feature-universal-collector.md` 里曾把小红书列为 YAML 配置示例，假设单次 HTTP 请求 + LLM 提取即可。实际调研后发现这条路走不通：

- 搜索页/详情页需要登录态才能拿到完整内容，纯 HTTP 请求拿不到可用 HTML，必须用 Playwright 渲染并注入 cookie，让浏览器自身的 JS 处理签名和登录态。
- 评论区抓取需要"搜索列表 → 进笔记详情页 → 加载评论区"的多阶段流程，`UniversalCollector` 当前是单次 fetch + extract 的模型，不支持多阶段抓取。

因此小红书单独实现 `XiaohongshuCollector`，承担多阶段编排逻辑，但底层抓取复用/新增的 `PlaywrightFetcher` 组件（见下文「需要新增的基础设施」）。

### 采集流程

```
WorkflowService.collect()
  → CollectorFactory.create("xiaohongshu", source)
  → XiaohongshuCollector.collect(topics, config)
      for each topic:
        for each keyword in topic.expanded_hints:
          搜索列表页（Playwright + cookie 注入）→ 笔记摘要列表（标题/链接/简介）
          for each note:
            进笔记详情页（Playwright + cookie）
            if config.content_mode == "imitate":
              抓正文全文 → QuestionItem(content_mode="imitate")
            if config.content_mode == "answer":
              额外滚动加载评论区 → 逐条提问映射为 QuestionItem(content_mode="answer")
              （某条笔记评论加载失败时跳过该笔记，不影响其他笔记的采集结果）
```

### 数据模型变更

- `WorkflowConfig` 新增 `content_mode: str = "answer"`（alias `contentMode`），知乎不传时保持现状。
- `QuestionItem` 新增 `content_mode: str = "answer"`（alias `contentMode`），由采集器写入每条结果，确保草稿保存/刷新后仍能判断该用哪种生成逻辑，不依赖请求时的临时上下文。

### 生成层分支

`DeepSeekAnswerGenerator.generate_answer` / `polish_answer` 根据 `item.content_mode` 选择提示词模板：

- `"answer"`：沿用现有"请围绕下面这个{platform}问题写一篇适合发布到对应平台的原创回答"话术，不变。
- `"imitate"`：新增模板，要求"参考下面这篇笔记的选题角度和写作风格，创作一篇全新的原创笔记，不要照抄原文内容，只学习其风格和结构"，避免输出变成抄袭/洗稿。

### 前端改动

- `frontend/src/features/workspace/defaults.ts` 的 `supportedPlatforms` 新增 `{ id: "xiaohongshu", label: "小红书" }`。
- CollectPage 操作栏现有"来源"选择器按平台动态切换语义：
  - 平台 = 知乎：保持现有"来源"选择器（自动选择/官方API/网页抓取），行为不变。
  - 平台 = 小红书：替换为"内容模式"选择器（回答模式 / 仿写模式），对应 `content_mode=answer/imitate`。
- 问题列表条目副标题在 `content_mode=imitate` 时改为"小红书 · 笔记仿写参考"，避免误以为仍是"待回答问题"。
- 右侧生成区按钮文案在仿写模式下显示"生成仿写笔记"，底层 `AnswerPanel`/`MarkdownEditor` 组件结构不变。

### 需要新增的基础设施

调研确认：`universal_collector.py` 中已经引用了 `PlaywrightFetcher`（`from .fetchers.playwright_fetcher import PlaywrightFetcher`），但该文件**实际并不存在**（`fetchers/` 目录下目前只有 `http_fetcher.py`），`playwright` 也尚未加入 `pyproject.toml` 依赖。这意味着：

- 本次需要**新建** `app/infrastructure/collectors/fetchers/playwright_fetcher.py`，支持启动 headless Chromium、注入 cookie 字符串、等待页面渲染完成后返回 DOM HTML。
- 需要在 `pyproject.toml` 添加 `playwright` 依赖，并在环境搭建文档里补充 `playwright install chromium` 步骤。
- 这个 `PlaywrightFetcher` 实现后，`UniversalCollector` 的 `fetcher: playwright` 配置项也会随之可用，是一个一次实现两处受益的基础设施投入。

### 错误处理与已知风险

- **Cookie 失效**：识别"页面被重定向到登录页/出现登录浮层"特征，明确抛出"小红书登录态已失效，请重新导出 cookie"类错误，不能静默返回空列表。
- **滑块验证码/风控拦截**：识别验证码页特征后直接跳过并报错，不把验证码页面内容喂给 LLM 提取器。
- **请求节流**：关键词之间需要加访问间隔，Playwright 访问比知乎现有 API 请求更慢、并发也更容易被判定为异常流量。
- **评论区抓取失败要降级**：某条笔记评论区加载失败时只跳过该笔记，不影响同批次其他笔记的采集结果。
- **新增运行时依赖**：Playwright 需要安装浏览器二进制，环境搭建文档需要补充说明。

### 环境变量

新增 `XIAOHONGSHU_COOKIE_FILE`，约定与现有 `ZHIHU_COOKIE_FILE` 一致：存放已登录小红书账号的 cookie 文件路径。

### 测试策略

参照 `tests/test_zhihu_import.py` 的现有模式（`unittest.IsolatedAsyncioTestCase` + `AsyncMock` mock 网络请求，不做真实联调）：

- Mock `PlaywrightFetcher.fetch`（或 `XiaohongshuCollector` 内部抓取方法），用预先准备的 HTML 样例验证"清洗 → 解析笔记字段/评论字段 → 映射 QuestionItem"逻辑。
- 验证 `content_mode="answer"` 与 `"imitate"` 两种配置下生成的 prompt 文案确实走了对应模板（断言关键措辞，不真调用 LLM）。
- 用"检测到登录页特征"的 HTML 样例验证采集器抛出明确异常，而不是返回空列表悄悄吞掉问题。
- 不对真实浏览器/真实账号做自动化联调测试（不稳定，依赖网络和登录态）。

## 不受影响的现有功能

- 知乎采集器（web/official）逻辑完全保留。
- `WorkflowService.collect()` 调用签名不变。
- `/api/workflow/collect` 接口契约不变。
- `content_mode` 默认值保持知乎现状（行为等同于未引入此字段之前）。

## 实现顺序（供后续 writing-plans 阶段细化）

1. 数据模型：`WorkflowConfig` / `QuestionItem` 新增 `content_mode` 字段。
2. 新建 `PlaywrightFetcher`（支持 cookie 注入），添加 `playwright` 依赖。
3. `XiaohongshuCollector` 骨架 + 笔记列表搜索（关键词 → 笔记摘要列表）。
4. 笔记详情抓取 + `content_mode="imitate"` 路径打通。
5. 评论区抓取 + `content_mode="answer"` 路径打通。
6. 生成层 prompt 分支（`imitate` 模板）。
7. 前端：平台选项 + 内容模式选择器 + 列表/按钮文案区分。
8. 测试：mock Playwright fetch 结果，覆盖解析、`content_mode` 分支、登录失效/验证码识别场景。
9. 错误处理与节流逻辑补齐。

## 依赖

- 依赖新建的 `PlaywrightFetcher`（不存在现成实现，需要本次新建，详见「需要新增的基础设施」）。
- 需要用户提供已登录的小红书账号 cookie 文件，用于本地开发验证。
