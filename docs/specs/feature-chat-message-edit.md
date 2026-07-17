# Feature: Chat Message Edit & Branching — 对话消息编辑与多分支版本切换

## 背景（Background）
当前 Chat 功能仅支持单向线性多轮对话，用户无法修改已发送的提问。若用户需要调整提问，只能重新开启新对话，或在原对话中发送新提问，这导致：
1. 无法方便地在同一个上下文脉络中对比不同提问版本下的 AI 回答。
2. 历史无用提问和回答堆积在会话中，影响阅读和后续的上下文质量。

为了解决该问题，我们需要为对话功能增加“复制提问”和“编辑提问”能力。点击编辑后，用户可修改已发送的提问并重新运行 Agent 生成回答。对于同一个提问位置，系统应支持版本分支切换（如 `< 2 / 2 >`），切换后，下游的所有对话内容也将随之切换到对应分支的上下文。

## 目标（Goal）
1. 在 Chat 面板的用户提问消息下方添加复制（Copy）和编辑（Edit）按钮。
2. 点击复制按钮，一键复制提问内容至剪贴板，并提供微动效反馈（图标变为 Check 图标并在 2 秒后恢复）。
3. 点击编辑按钮，将原提问卡片替换为内联编辑框，支持取消编辑和发送修改。
4. 发送修改后，系统在当前消息节点前分叉出新提问分支，并调用 Agent 重新生成回答，不影响已有的其他分支。
5. 当某个消息节点存在多个提问分支时，在消息卡片下方显示分支切换控件（如 `< 2 / 2 >`），允许用户在多个分支及其后续对话之间来回切换。

## 非目标（Non-Goals）
1. 不支持编辑 AI 的回答（Assistant 角色消息）。
2. 不支持合并不同分支的回答内容，各分支完全独立。
3. 不对历史的分支提供“批量删除”或“分支重命名”功能。

## 用户故事（User Stories）
1. 作为创作者，当我觉得上一个提问表达不够准确时，我希望能直接编辑该提问，以便获得更精确的回答，而不需要重新开启一个新对话。
2. 作为创作者，当我尝试了两种不同的提问方式后，我希望能够快速切换这两个版本的提问，以便对比和查看不同提问下的采集结果或创作回答。
3. 作为创作者，我希望在消息卡片下能够一键复制我的提问，以便我复用此 Prompt。

## 功能需求（Requirements）
1. **复制功能**：
   - 提取当前消息的 `content`，复制到系统剪贴板。
2. **编辑与发送功能**：
   - 仅用户发送的消息（`role == "user"`）支持编辑。
   - 点击编辑进入编辑模式，展示包含“取消”和“发送”按钮的输入框。
   - 编辑框内默认填入原消息文本。
   - 点击“取消”退出编辑，恢复原样。
   - 点击“发送”以新提问内容发起 SSE 对话流，传递 `parentMessageId` 指向当前消息的父节点。
3. **多版本分支与切换**：
   - 当同一父消息下存在多个子消息时，它们互为“兄弟节点（Siblings）”，即为该位置的多个提问版本。
   - 存在多个兄弟节点时，在提问消息卡片下方显示 `< 当前版本 / 总版本 >` 切换控件。
   - 点击 `<` 或 `>` 切换版本时，自动定位到选中版本在数据库中的最新叶子节点（Leaf Message），并更新前端 `activeLeafMessageId`，实现整个对话分支的无缝切换。
4. **数据库设计**：
   - `messages` 表增加 `parent_message_id` 外键列，支持自关联。
   - 旧数据的兼容处理：若 `parent_message_id` 为 NULL，根据 `created_at` 的 chronological 顺序作为虚拟父子关系。
5. **接口设计**：
   - 消息发送接口 `POST /api/chats/{chat_id}/messages/stream` 增加可选的 `parentMessageId` 输入参数。
   - 消息列表接口 `GET /api/chats/{chat_id}/messages` 返回的每条消息实体中包含 `parentMessageId`。

## 验收标准（Acceptance Criteria）
1. 用户消息下方能正确显示 Copy 和 Edit 图标。
2. 点击 Copy 图标后，文本成功复制，图标变为 Check 图标并在 2 秒后恢复。
3. 点击 Edit 图标后，编辑卡片以蓝色边框、圆角输入框的形式展示，内含“取消”和“发送”按钮，布局与截图一致。
4. 点击“取消”后，正常恢复提问，无数据变化。
5. 修改提问并点击“发送”后，能够正常触发流式响应，生成的新回答与新提问正确关联，且该提问卡片下方出现类似 `< 2 / 2 >` 的切换标志。
6. 点击 `<` 和 `>` 箭头可以来回切换不同的问题版本，同时该问题下方对应的 AI 回答也随之切换。
7. 切换到历史版本后，在此基础上继续发送新消息，其 parentMessageId 必须为选中版本的 AI 回答，能够继续该分支的对话。
8. 历史已存在的旧对话数据能够正常读取并在线性流中展示。

## 边界情况（Edge Cases）
1. **正在生成回答时编辑消息**：若 Agent 正在流式输出中（`isStreaming` 为 true），禁用编辑按钮和分支切换控件。
2. **编辑第一个提问**：若编辑会话中的首个提问，其 `parent_message_id` 仍为 NULL，但会生成一个新的兄弟提问，同样支持多版本切换。
3. **网络或生成失败**：若修改后发送失败，会产生一个 `error` 类型的子节点，允许用户再次编辑或切回旧版本。
4. **多个分支下游深度不同**：分支 A 包含 3 轮对话，分支 B 仅包含 1 轮。当切换到分支 B 时，下游仅显示 1 轮；切回 A 时，显示 3 轮。

## 交互与界面行为（UX / UI Behavior）
1. **图标样式**：
   - 使用 Lucide 库中的 `Copy`, `Check`, `Pencil`, `ChevronLeft`, `ChevronRight` 图标。
   - 默认状态下图标颜色为低对比度浅灰色（`text-muted-foreground/60`），悬浮时高亮（`hover:text-muted-foreground`）。
2. **编辑输入框**：
   - 蓝色高亮圆角边框，自带轻微阴影，内部 Textarea 自动聚焦并可自适应高度。
   - 底部右侧并排“取消”和“发送”按钮，在流式加载期间禁用“发送”并显示 Loading。
3. **版本切换控件**：
   - 结构为 `[Copy] [Edit] < 1 / 2 >`，保持水平排列。
   - 处于首个版本时，左箭头置灰不可点击；处于最后一个版本时，右箭头置灰。

## 数据模型（Data Model）
1. **数据库表变更**：
   - `messages` 表新增列：`parent_message_id` (UUID, NULL, foreign key pointing to `messages.id`).
2. **FastAPI Pydantic 模型变更**：
   - `SendMessageRequest` 增加 `parentMessageId` (str | None) 字段。
   - 路由层返回的消息结构中增加 `parentMessageId` 字段。

## 接口设计（API / Interface Design）
1. **发送消息接口**：
   - `POST /api/chats/{chat_id}/messages/stream`
   - 请求体增加 `"parentMessageId": "uuid-string-or-null"`。
2. **获取消息列表接口**：
   - `GET /api/chats/{chat_id}/messages`
   - 返回的数据列表中，每条消息对象包含 `parentMessageId` 字段。

## 架构说明（Architecture Notes）
1. **LangGraph 隔离**：
   - 每次 graph 运行传入的 messages 为当前 activeLeafMessageId 溯源到根节点的完整有序列表。
   - 传入的 `thread_id` 可以使用本次 run_id 或 new_user_message_id，实现运行时状态的完全隔离，避免不同分支在 checkpoint 中产生干扰。
2. **单源信赖链（Single Source of Truth）**：
   - 消息的树形关系完全保存在后端 messages 表的 `parent_message_id` 链条中。
   - 前端加载全部 messages 后，基于 `parent_message_id` 进行树形解析，自动匹配并构建出当前 `activeLeafMessageId` 代表的线性对话历史进行展示。

## 测试策略（Testing Strategy）
1. **后端单元测试**：
   - 编写 `tests/test_chat_branching.py`：测试包含不同 `parent_message_id` 的消息保存，验证 `get_messages` 能够正确返回树形结构所需的字段。
   - 测试带 `parent_message_id` 参数的流式发送接口。
2. **前端单元测试 / 页面手动验证**：
   - 确认 Copy、Edit 状态切换。
   - 确认版本切换能正确联动更新 leaf 节点及 messages 过滤。

## 风险（Risks）
1. **数据库升级风险**：由于现有环境存在历史消息数据，必须编写迁移脚本或在模型层处理 NULL 值的兼容性，防止查询崩溃。已通过前端“虚拟父子节点链接法”进行兜底防范。
2. **流式状态并发**：若用户快速切换分支，可能导致当前流式渲染错位。需要确保在 isStreaming 状态下置灰并禁用分支切换和编辑功能。

## 待确认问题（Open Questions）
无。
