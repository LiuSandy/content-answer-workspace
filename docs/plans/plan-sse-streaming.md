# SSE 流式输出实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有大模型调用改为 SSE 流式输出，使用户能实时看到生成过程，而不是等待完整响应。

**Architecture:** 后端在 `deepseek_client.py` 中增加流式生成器方法（`stream=True`），新增 `/stream` 后缀的 SSE 端点，前端用 `fetch` + `ReadableStream` 解析 `data: {...}\n\n` 格式的 SSE 事件。现有 JSON 端点保留不变以保证兼容性，前端切换为调用新的流式端点。

**Tech Stack:** Python AsyncGenerator, FastAPI StreamingResponse, LangGraph astream_events, TypeScript ReadableStream

## Global Constraints

- SSE 事件格式统一为 `data: {JSON}\n\n`，JSON 字段 `type` 区分事件类型
- 现有 REST 端点保持不变（不删除、不修改行为）
- 后端新增端点全部带 `/stream` 后缀
- 前端不引入第三方 SSE 库，使用原生 `fetch` + `ReadableStream`
- 不改变 Zustand store 结构，通过已有 `setQuestionAnswer` / `setQuestionItem` 实现增量更新

---

## SSE 事件类型定义（所有端点共用）

```
data: {"type": "chunk", "text": "..."}\n\n          -- LLM token 片段
data: {"type": "item_start", "itemId": "..."}\n\n    -- 批量生成：某条问题开始
data: {"type": "item_done", "itemId": "...", "item": {...}}\n\n  -- 批量生成：某条完成
data: {"type": "done", "data": {...}}\n\n             -- 流结束，附带完整结果
data: {"type": "error", "message": "..."}\n\n         -- 出错
```

---

## 文件清单

**新建：**
- `app/api/routes/stream.py` — 工作流流式端点（generate-one/stream、polish-one/stream、generate/stream）
- `frontend/src/lib/sse.ts` — 前端 SSE 工具函数

**修改：**
- `app/infrastructure/llm/deepseek_client.py` — 增加 `generate_answer_stream`、`polish_answer_stream`、`call_raw_stream` 三个 AsyncGenerator 方法
- `app/api/routes/agent.py` — 增加 `/api/agent/conversation/stream` 和 `/api/agent/chat/stream`
- `app/server.py` — 注册 stream_router
- `frontend/src/features/workspace/workflow-api.ts` — 增加五个流式 API 函数
- `frontend/src/features/workspace/use-workspace.ts` — 将 generateOne、polishOne、generateAll 三个 mutation 改为流式
- `frontend/src/features/workspace/chat-page.tsx` — 对话页面改用流式端点
- `frontend/src/features/workspace/chat-message-thread.tsx` — 支持 `streamingContent` 展示流式消息
- `frontend/src/features/workspace/refinement-chat.tsx` — 精修聊天改用流式
- `frontend/src/features/workspace/hotlist-analysis-panel.tsx` — 热榜分析改用流式

---

### Task 1: 后端 — `deepseek_client.py` 增加三个流式方法

**Files:**
- Modify: `app/infrastructure/llm/deepseek_client.py`

**Interfaces:**
- Produces:
  - `DeepSeekAnswerGenerator.generate_answer_stream(item, answer_style, cta_text, system_prompt, generation_prompt, content_constraint) -> AsyncIterator[str]`
  - `DeepSeekAnswerGenerator.polish_answer_stream(item, current_answer, answer_style, cta_text, system_prompt, generation_prompt, content_constraint) -> AsyncIterator[str]`
  - `DeepSeekAnswerGenerator.call_raw_stream(system, user) -> AsyncIterator[str]`

- [ ] **Step 1: 在 `generate_answer` 方法之后，在 `DeepSeekAnswerGenerator` 类中添加 `generate_answer_stream` 方法**

在 `deepseek_client.py` 第 90 行（`raise ValueError("DeepSeek returned empty answer content")`）之后插入：

```python
    async def generate_answer_stream(
        self,
        item: QuestionItem,
        answer_style: str,
        cta_text: str,
        system_prompt: str,
        generation_prompt: str,
        content_constraint: str | None = None,
    ) -> AsyncIterator[str]:
        """流式调用 DeepSeek 生成回答；逐 token yield 给调用方，供 SSE 端点推送。"""

        client = self.get_client()
        model = get_required_env("DEEPSEEK_MODEL")
        platform_label = item.platform or "zhihu"
        if item.content_mode == "imitate":
            intro_line = (
                f"请参考下面这篇{platform_label}笔记的选题角度和写作风格，创作一篇全新的原创笔记，"
                f"不要照抄原文内容，只学习其风格和结构。整体风格要求：{answer_style}"
            )
        else:
            intro_line = f"请围绕下面这个{platform_label}问题写一篇适合发布到对应平台的原创回答，整体风格要求：{answer_style}"
        prompt_parts = [
            intro_line,
            "",
            "全局生成规则：",
            generation_prompt,
        ]
        if content_constraint and content_constraint.strip():
            prompt_parts += [
                "",
                f"内容约束（必须严格遵守）：回答只能围绕「{content_constraint.strip()}」展开，不要回答与此无关的内容。",
            ]
        prompt_parts += [
            "",
            f"平台：{platform_label}",
            f"问题标题：{item.title}",
            f"问题链接：{item.url}",
            f"问题分类：{item.topic or '未分类'}",
            f"问题摘要：{item.excerpt or '无'}",
            f"结尾引流文案：{cta_text}",
        ]
        prompt = "\n".join(prompt_parts)
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
```

注意：需要在文件顶部 `from __future__ import annotations` 行下方补充导入：

```python
from collections.abc import AsyncIterator
```

- [ ] **Step 2: 在 `polish_answer` 方法之后添加 `polish_answer_stream` 方法**

在 `raise ValueError("DeepSeek returned empty polish content")` 之后（第 153 行附近）插入：

```python
    async def polish_answer_stream(
        self,
        item: QuestionItem,
        current_answer: str,
        answer_style: str,
        cta_text: str,
        system_prompt: str,
        generation_prompt: str,
        content_constraint: str | None = None,
    ) -> AsyncIterator[str]:
        """流式润色回答；逐 token yield，供 SSE 端点推送。"""

        client = self.get_client()
        model = get_required_env("DEEPSEEK_MODEL")
        platform_label = item.platform or "zhihu"
        if item.content_mode == "imitate":
            intro_line = (
                f"请对下面这篇{platform_label}笔记进行润色改写。要求：保留原有核心创意和结构，不要引入新观点；"
                f"改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}"
            )
        else:
            intro_line = (
                f"请对下面这篇{platform_label}回答进行润色改写。要求：保留原有核心观点和论证思路，不要引入新观点；"
                f"改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}"
            )
        prompt_parts = [
            intro_line,
            "",
            "全局生成规则：",
            generation_prompt,
        ]
        if content_constraint and content_constraint.strip():
            prompt_parts += [
                "",
                f"内容约束（必须严格遵守）：回答只能围绕「{content_constraint.strip()}」展开，不要回答与此无关的内容。",
            ]
        prompt_parts += [
            "",
            f"平台：{platform_label}",
            f"问题标题：{item.title}",
            f"问题链接：{item.url}",
            f"问题分类：{item.topic or '未分类'}",
            f"结尾引流文案：{cta_text}",
            "",
            "当前回答草稿（请以此为基础润色，不要大幅偏离原有内容）：",
            current_answer,
        ]
        prompt = "\n".join(prompt_parts)
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
```

- [ ] **Step 3: 在 `call_raw` 方法之后添加 `call_raw_stream` 方法**

在第 174 行（`raise ValueError("LLM returned empty content")`）之后插入：

```python
    async def call_raw_stream(self, system: str, user: str) -> AsyncIterator[str]:
        """通用 LLM 流式调用，不附加任何业务提示词。供 Agent 层 SSE 端点使用。"""
        client = self.get_client()
        model = get_required_env("DEEPSEEK_MODEL")
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
```

- [ ] **Step 4: 手动验证语法正确（无测试，改动纯属添加方法）**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace
uv run python -c "from app.infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/llm/deepseek_client.py
git commit -m "feat: add streaming generator methods to DeepSeekAnswerGenerator"
```

---

### Task 2: 后端 — 新建工作流流式路由 `app/api/routes/stream.py`

**Files:**
- Create: `app/api/routes/stream.py`

**Interfaces:**
- Consumes: `DeepSeekAnswerGenerator.generate_answer_stream()`, `DeepSeekAnswerGenerator.polish_answer_stream()` (from Task 1)
- Consumes: `WorkflowService.collect()`, `get_workflow_config()`, `generate_answer_with_images()` (已有)
- Produces:
  - `POST /api/workflow/generate-one/stream` → SSE stream
  - `POST /api/workflow/polish-one/stream` → SSE stream
  - `POST /api/workflow/generate/stream` → SSE stream

- [ ] **Step 1: 创建文件 `app/api/routes/stream.py`**

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...application.workflow_service import WorkflowService, normalize_platform
from ...core.config import get_workflow_config, load_env_file
from ...infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ...models import PolishPayload, RegeneratePayload, SessionPayload
from ...services.image_service import GeneratedImagePayload, ImageGenerationService

router = APIRouter(prefix="/api/workflow", tags=["stream"])

_answer_generator = DeepSeekAnswerGenerator()
_image_service = ImageGenerationService()
workflow_service = WorkflowService()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _make_sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/generate-one/stream")
async def generate_one_stream(payload: RegeneratePayload) -> StreamingResponse:
    """流式生成单条回答；逐 token 推送，完成后以 done 事件携带完整问题对象。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            load_env_file()
            platform = normalize_platform(payload.platform or payload.item.platform)
            item = payload.item.model_copy(update={"platform": platform})
            config = get_workflow_config(
                {
                    "platform": platform,
                    "answerStyle": payload.answer_style,
                    "systemPrompt": payload.system_prompt,
                    "generationPrompt": payload.generation_prompt,
                }
            )
            full_text = ""
            async for chunk in _answer_generator.generate_answer_stream(
                item,
                payload.answer_style or config.answer_style,
                config.cta_text,
                payload.system_prompt or config.system_prompt,
                payload.generation_prompt or config.generation_prompt,
                payload.content_constraint or None,
            ):
                full_text += chunk
                yield _sse({"type": "chunk", "text": chunk})

            try:
                images = await _image_service.generate_images_for_answer(item, full_text)
            except ValueError as e:
                if "Missing required env: IMAGE_" not in str(e):
                    raise
                images = GeneratedImagePayload(images=[], imagePrompts=[])

            final_item = item.model_copy(
                update={
                    "answer": full_text.strip(),
                    "images": images.get("images", []),
                    "image_prompts": images.get("imagePrompts", []),
                }
            )
            yield _sse({"type": "done", "data": {"item": final_item.model_dump(by_alias=True)}})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())


@router.post("/polish-one/stream")
async def polish_one_stream(payload: PolishPayload) -> StreamingResponse:
    """流式润色单条回答；逐 token 推送，完成后以 done 事件携带完整问题对象。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            load_env_file()
            platform = normalize_platform(payload.platform or payload.item.platform)
            item = payload.item.model_copy(update={"platform": platform})
            config = get_workflow_config(
                {
                    "platform": platform,
                    "answerStyle": payload.answer_style,
                    "systemPrompt": payload.system_prompt,
                    "generationPrompt": payload.generation_prompt,
                }
            )
            full_text = ""
            async for chunk in _answer_generator.polish_answer_stream(
                item,
                payload.current_answer,
                payload.answer_style or config.answer_style,
                config.cta_text,
                payload.system_prompt or config.system_prompt,
                payload.generation_prompt or config.generation_prompt,
                payload.content_constraint or None,
            ):
                full_text += chunk
                yield _sse({"type": "chunk", "text": chunk})

            final_item = item.model_copy(update={"answer": full_text.strip()})
            yield _sse({"type": "done", "data": {"item": final_item.model_dump(by_alias=True)}})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())


@router.post("/generate/stream")
async def generate_stream(payload: SessionPayload) -> StreamingResponse:
    """批量流式生成回答；每条问题依次发 item_start → chunk* → item_done，全部完成后发 all_done。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            load_env_file()
            platform = normalize_platform(payload.platform)
            config = get_workflow_config(
                {
                    "platform": platform,
                    "answerStyle": payload.answer_style,
                    "systemPrompt": payload.system_prompt,
                    "generationPrompt": payload.generation_prompt,
                }
            )
            done_items = []
            for raw_item in payload.items:
                item = raw_item.model_copy(
                    update={"platform": normalize_platform(raw_item.platform or platform)}
                )
                yield _sse({"type": "item_start", "itemId": item.id})
                full_text = ""
                async for chunk in _answer_generator.generate_answer_stream(
                    item,
                    payload.answer_style or config.answer_style,
                    config.cta_text,
                    payload.system_prompt or config.system_prompt,
                    payload.generation_prompt or config.generation_prompt,
                    payload.content_constraint or None,
                ):
                    full_text += chunk
                    yield _sse({"type": "chunk", "itemId": item.id, "text": chunk})

                try:
                    images = await _image_service.generate_images_for_answer(item, full_text)
                except ValueError as e:
                    if "Missing required env: IMAGE_" not in str(e):
                        raise
                    images = GeneratedImagePayload(images=[], imagePrompts=[])

                final_item = item.model_copy(
                    update={
                        "answer": full_text.strip(),
                        "images": images.get("images", []),
                        "image_prompts": images.get("imagePrompts", []),
                    }
                )
                done_items.append(final_item)
                yield _sse({"type": "item_done", "itemId": item.id, "item": final_item.model_dump(by_alias=True)})

            yield _sse({"type": "done", "data": {"items": [i.model_dump(by_alias=True) for i in done_items]}})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())
```

- [ ] **Step 2: 验证语法**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace
uv run python -c "from app.api.routes.stream import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/api/routes/stream.py
git commit -m "feat: add SSE streaming endpoints for workflow generate and polish"
```

---

### Task 3: 后端 — Agent 流式端点

**Files:**
- Modify: `app/api/routes/agent.py`

**Interfaces:**
- Consumes: `DeepSeekAnswerGenerator.call_raw_stream()` (Task 1)
- Consumes: LangGraph `graph.astream_events()` (LangGraph 已有 API)
- Produces:
  - `POST /api/agent/conversation/stream` → SSE stream（对话逐 token）
  - `POST /api/agent/chat/stream` → SSE stream（精修/分析逐 token）

- [ ] **Step 1: 在 `agent.py` 顶部的 import 区域补充导入**

在现有 import 末尾（第 6 行 `from ...services.session_service import update_session_title` 之后）添加：

```python
import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from ...infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ...services.hotlist_service import fetch_hotlist
```

同时在文件内（`router = APIRouter()` 之后）添加辅助函数和 generator 实例：

```python
_answer_gen = DeepSeekAnswerGenerator()

_ANALYSIS_SYSTEM_PROMPT = """
你是内容策略分析师。分析知乎热榜数据，严格按以下 JSON 格式输出：
{
  "topicDistribution": [{"field": "领域", "count": N, "examples": ["标题"]}],
  "contentOpportunities": [{"direction": "方向", "reason": "理由"}],
  "audienceMood": "情绪基调",
  "recommendations": [{"topic": "选题", "reason": "理由", "keywords": ["词"]}]
}
只返回 JSON，不要其他说明。
""".strip()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _make_sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 2: 在文件末尾（第 101 行之后）追加两个流式端点**

```python
@router.post("/api/agent/conversation/stream")
async def agent_conversation_stream(request: ConversationRequest, http_request: Request) -> StreamingResponse:
    """对话页面流式接口；使用 LangGraph astream_events 逐 token 推送模型回复。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            graph = http_request.app.state.conversation_graph
            config = {"configurable": {"thread_id": request.sessionId}}
            existing_state = await graph.aget_state(config)
            is_first_message = not existing_state.values.get("messages")
            full_reply = ""
            async for event in graph.astream_events(
                {"messages": [{"role": "user", "content": request.message}]},
                config=config,
                version="v2",
            ):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        full_reply += chunk.content
                        yield _sse({"type": "chunk", "text": chunk.content})

            if is_first_message:
                update_session_title(request.sessionId, request.message[:20])

            yield _sse({"type": "done", "data": {"reply": full_reply}})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())


@router.post("/api/agent/chat/stream")
async def agent_chat_stream(request: AgentChatRequest) -> StreamingResponse:
    """精修/热榜分析流式接口；refinement 流式输出修改后的回答，analysis 流式输出分析 JSON。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            if request.questionId:
                # 精修模式：流式输出修改后的回答文本
                current_answer = request.currentAnswer or ""
                instruction = request.message
                prompt = "\n".join([
                    "请严格按照用户指令修改以下回答。",
                    "只改动用户指定的部分，其余内容保持原样，不要自行发挥。",
                    "",
                    f"用户指令：{instruction}",
                    "",
                    "当前回答：",
                    current_answer,
                ])
                full_answer = ""
                async for chunk in _answer_gen.call_raw_stream(
                    system="你是专业的内容编辑助手。",
                    user=prompt,
                ):
                    full_answer += chunk
                    yield _sse({"type": "chunk", "text": chunk})

                short = instruction[:30]
                yield _sse({
                    "type": "done",
                    "data": {
                        "reply": "已按您的要求完成修改。",
                        "answerUpdated": True,
                        "updatedAnswer": full_answer.strip(),
                        "operationSummary": f"修改：{short}",
                    },
                })
            else:
                # 分析模式：先获取热榜，再流式输出分析
                hotlist_response = await fetch_hotlist(limit=30)
                items = [item.model_dump(by_alias=True) for item in hotlist_response.items]
                lines = [
                    f"{item['rank']}. {item['title']}（热度：{item['heat']}）\n   {item.get('summary', '')}"
                    for item in items
                ]
                user_prompt = f"以下是当前知乎热榜 {len(items)} 条内容：\n\n" + "\n".join(lines)
                full_reply = ""
                async for chunk in _answer_gen.call_raw_stream(
                    system=_ANALYSIS_SYSTEM_PROMPT,
                    user=user_prompt,
                ):
                    full_reply += chunk
                    yield _sse({"type": "chunk", "text": chunk})

                yield _sse({
                    "type": "done",
                    "data": {
                        "reply": full_reply.strip(),
                        "answerUpdated": False,
                        "updatedAnswer": None,
                        "operationSummary": "热榜分析",
                    },
                })
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())
```

- [ ] **Step 3: 验证语法**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace
uv run python -c "from app.api.routes.agent import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/api/routes/agent.py
git commit -m "feat: add SSE streaming endpoints for agent conversation and chat"
```

---

### Task 4: 后端 — 注册 stream router

**Files:**
- Modify: `app/server.py`

**Interfaces:**
- Consumes: `app/api/routes/stream.py` (Task 2)
- Produces: 所有新 `/api/workflow/**/stream` 端点对外可访问

- [ ] **Step 1: 在 `server.py` 顶部 import 区域添加**

在第 13 行（`from .api.routes.workflow import router as workflow_router`）之后：

```python
from .api.routes.stream import router as stream_router
```

- [ ] **Step 2: 在 `app.include_router(workflow_router)` 之后添加**

```python
app.include_router(stream_router)
```

- [ ] **Step 3: 验证语法**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace
uv run python -c "from app.server import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/server.py
git commit -m "feat: register stream router in FastAPI app"
```

---

### Task 5: 前端 — 创建 SSE 工具函数

**Files:**
- Create: `frontend/src/lib/sse.ts`

**Interfaces:**
- Produces:
  ```typescript
  type SseEvent<T> =
    | { type: "chunk"; text: string; itemId?: string }
    | { type: "item_start"; itemId: string }
    | { type: "item_done"; itemId: string; item: unknown }
    | { type: "done"; data: T }
    | { type: "error"; message: string };

  type SseCallbacks<T> = {
    onChunk?: (text: string, itemId?: string) => void;
    onItemStart?: (itemId: string) => void;
    onItemDone?: (itemId: string, item: unknown) => void;
    onDone?: (data: T) => void;
    onError?: (message: string) => void;
  };

  export async function streamPost<T>(url: string, body: unknown, callbacks: SseCallbacks<T>): Promise<void>
  ```

- [ ] **Step 1: 创建 `frontend/src/lib/sse.ts`**

```typescript
export type SseEvent<T> =
  | { type: "chunk"; text: string; itemId?: string }
  | { type: "item_start"; itemId: string }
  | { type: "item_done"; itemId: string; item: unknown }
  | { type: "done"; data: T }
  | { type: "error"; message: string };

export type SseCallbacks<T> = {
  onChunk?: (text: string, itemId?: string) => void;
  onItemStart?: (itemId: string) => void;
  onItemDone?: (itemId: string, item: unknown) => void;
  onDone?: (data: T) => void;
  onError?: (message: string) => void;
};

export async function streamPost<T>(
  url: string,
  body: unknown,
  callbacks: SseCallbacks<T>,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok || !response.body) {
    callbacks.onError?.(`HTTP ${response.status}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      try {
        const event = JSON.parse(raw) as SseEvent<T>;
        if (event.type === "chunk") callbacks.onChunk?.(event.text, event.itemId);
        else if (event.type === "item_start") callbacks.onItemStart?.(event.itemId);
        else if (event.type === "item_done") callbacks.onItemDone?.(event.itemId, event.item);
        else if (event.type === "done") callbacks.onDone?.(event.data);
        else if (event.type === "error") callbacks.onError?.(event.message);
      } catch {
        // 忽略非 JSON 行
      }
    }
  }
}
```

- [ ] **Step 2: 验证 TypeScript 类型检查**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace/frontend
bun run typecheck
```

Expected: 无报错（或仅有与此文件无关的已有错误）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/sse.ts
git commit -m "feat: add streamPost SSE utility for frontend streaming"
```

---

### Task 6: 前端 — `workflow-api.ts` 增加流式 API 函数

**Files:**
- Modify: `frontend/src/features/workspace/workflow-api.ts`

**Interfaces:**
- Consumes: `streamPost()` from `@/lib/sse` (Task 5)
- Produces:
  ```typescript
  // 单条生成流式
  export function streamGenerateOneAnswer(payload: GenerateOnePayload, callbacks: SseCallbacks<GenerateOneResponse>): Promise<void>
  // 单条润色流式
  export function streamPolishOneAnswer(payload: PolishOnePayload, callbacks: SseCallbacks<PolishOneResponse>): Promise<void>
  // 批量生成流式
  export function streamGenerateAllAnswers(payload: GenerateAllPayload, callbacks: SseCallbacks<GenerateAllResponse>): Promise<void>
  // 对话流式
  export function streamConversationMessage(payload: ConversationPayload, callbacks: SseCallbacks<ConversationResponse>): Promise<void>
  // Agent chat 流式
  export function streamAgentChat(payload: AgentChatPayload, callbacks: SseCallbacks<AgentChatResponse>): Promise<void>
  ```

- [ ] **Step 1: 在 `workflow-api.ts` 顶部 import 区域中增加**

在第 1 行（`import { apiDelete, apiGet, apiPost } from "@/lib/api";`）之后添加：

```typescript
import { streamPost, type SseCallbacks } from "@/lib/sse";
```

- [ ] **Step 2: 在文件末尾（`deleteSession` 函数之后）追加五个流式函数**

```typescript
export function streamGenerateOneAnswer(
  payload: GenerateOnePayload,
  callbacks: SseCallbacks<GenerateOneResponse>,
): Promise<void> {
  return streamPost("/api/workflow/generate-one/stream", payload, callbacks);
}

export function streamPolishOneAnswer(
  payload: PolishOnePayload,
  callbacks: SseCallbacks<PolishOneResponse>,
): Promise<void> {
  return streamPost("/api/workflow/polish-one/stream", payload, callbacks);
}

export function streamGenerateAllAnswers(
  payload: GenerateAllPayload,
  callbacks: SseCallbacks<GenerateAllResponse>,
): Promise<void> {
  return streamPost("/api/workflow/generate/stream", payload, callbacks);
}

export function streamConversationMessage(
  payload: ConversationPayload,
  callbacks: SseCallbacks<ConversationResponse>,
): Promise<void> {
  return streamPost("/api/agent/conversation/stream", payload, callbacks);
}

export function streamAgentChat(
  payload: AgentChatPayload,
  callbacks: SseCallbacks<AgentChatResponse>,
): Promise<void> {
  return streamPost("/api/agent/chat/stream", payload, callbacks);
}
```

- [ ] **Step 3: 类型检查**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace/frontend
bun run typecheck
```

Expected: 无新报错

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/workspace/workflow-api.ts
git commit -m "feat: add streaming API functions to workflow-api"
```

---

### Task 7: 前端 — `use-workspace.ts` 三个 mutation 改用流式

**Files:**
- Modify: `frontend/src/features/workspace/use-workspace.ts`

**Interfaces:**
- Consumes: `streamGenerateOneAnswer`, `streamPolishOneAnswer`, `streamGenerateAllAnswers` (Task 6)
- Consumes: `setQuestionAnswer(questionId, answer)` — store action，流式期间逐渐更新回答文本
- Consumes: `setQuestionItem(questionId, item)` — store action，流式结束后替换完整对象

- [ ] **Step 1: 在 `use-workspace.ts` 的 import 区域修改 `workflow-api.ts` 的导入**

把现有：
```typescript
import {
  collectWorkflow,
  generateAllAnswers,
  generateOneAnswer,
  getLatestSession,
  getSession,
  getWorkspaceConfig,
  parseQuestionUrl,
  polishOneAnswer,
  saveWorkspaceSession,
} from "./workflow-api";
```

替换为：
```typescript
import {
  collectWorkflow,
  getLatestSession,
  getSession,
  getWorkspaceConfig,
  parseQuestionUrl,
  saveWorkspaceSession,
  streamGenerateAllAnswers,
  streamGenerateOneAnswer,
  streamPolishOneAnswer,
} from "./workflow-api";
```

- [ ] **Step 2: 将 `generateOneMutation`（约第 321-342 行）替换为流式版本**

删除：
```typescript
  const generateOneMutation = useMutation({
    mutationFn: (item: QuestionItem) => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: GenerateOnePayload = {
        platform: selectedPlatform,
        item: withPlatform(item, selectedPlatform),
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
      };
      return generateOneAnswer(payload);
    },
    onSuccess: (data, item) => {
      setQuestionItem(item.id, withPlatform(data.item, selectedPlatform));
      setStatusMessage(`已生成：${item.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });
```

替换为：
```typescript
  const generateOneMutation = useMutation({
    mutationFn: (item: QuestionItem) => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: GenerateOnePayload = {
        platform: selectedPlatform,
        item: withPlatform(item, selectedPlatform),
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
      };
      return streamGenerateOneAnswer(payload, {
        onChunk: (text) => {
          setQuestionAnswer(
            item.id,
            (useWorkspaceStore.getState().questions.find((q) => q.id === item.id)?.answer ?? "") + text,
          );
        },
        onDone: (data) => {
          setQuestionItem(item.id, withPlatform(data.item, selectedPlatform));
        },
        onError: (message) => {
          setStatusMessage(message);
        },
      });
    },
    onSuccess: (_data, item) => {
      setStatusMessage(`已生成：${item.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });
```

- [ ] **Step 3: 将 `polishOneMutation`（约第 344-366 行）替换为流式版本**

删除：
```typescript
  const polishOneMutation = useMutation({
    mutationFn: (item: QuestionItem) => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: PolishOnePayload = {
        platform: selectedPlatform,
        item: withPlatform(item, selectedPlatform),
        currentAnswer: item.answer,
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
      };
      return polishOneAnswer(payload);
    },
    onSuccess: (data, item) => {
      setQuestionItem(item.id, withPlatform(data.item, selectedPlatform));
      setStatusMessage(`已润色：${item.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });
```

替换为：
```typescript
  const polishOneMutation = useMutation({
    mutationFn: (item: QuestionItem) => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: PolishOnePayload = {
        platform: selectedPlatform,
        item: withPlatform(item, selectedPlatform),
        currentAnswer: item.answer,
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
      };
      return streamPolishOneAnswer(payload, {
        onChunk: (text) => {
          setQuestionAnswer(
            item.id,
            (useWorkspaceStore.getState().questions.find((q) => q.id === item.id)?.answer ?? "") + text,
          );
        },
        onDone: (data) => {
          setQuestionItem(item.id, withPlatform(data.item, selectedPlatform));
        },
        onError: (message) => {
          setStatusMessage(message);
        },
      });
    },
    onSuccess: (_data, item) => {
      setStatusMessage(`已润色：${item.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });
```

- [ ] **Step 4: 将 `generateAllMutation`（约第 281-319 行）替换为流式版本**

删除：
```typescript
  const generateAllMutation = useMutation({
    mutationFn: () => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: GenerateAllPayload = {
        platform: selectedPlatform,
        topics: selectedTopic
          ? [
              {
                ...selectedTopic,
                systemPrompt: currentSystemPrompt,
                answerStyle: currentAnswerStyle,
              },
            ]
          : [],
        items: questions.map((item) => withPlatform(item, selectedPlatform)),
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
        maxPushCount,
      };
      return generateAllAnswers(payload);
    },
    onMutate: () => {
      setIsGeneratingAll(true);
      setStatusMessage("正在批量生成回答...");
    },
    onSuccess: (data) => {
      setQuestions(data.items.map((item) => withPlatform(item, selectedPlatform)));
      setStatusMessage(`已完成 ${data.items.length} 条回答生成。`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
    onSettled: () => {
      setIsGeneratingAll(false);
    },
  });
```

替换为：
```typescript
  const generateAllMutation = useMutation({
    mutationFn: () => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: GenerateAllPayload = {
        platform: selectedPlatform,
        topics: selectedTopic
          ? [
              {
                ...selectedTopic,
                systemPrompt: currentSystemPrompt,
                answerStyle: currentAnswerStyle,
              },
            ]
          : [],
        items: questions.map((item) => withPlatform(item, selectedPlatform)),
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
        maxPushCount,
      };
      const itemAnswers = new Map<string, string>();
      return streamGenerateAllAnswers(payload, {
        onItemStart: (itemId) => {
          itemAnswers.set(itemId, "");
        },
        onChunk: (text, itemId) => {
          if (!itemId) return;
          const prev = itemAnswers.get(itemId) ?? "";
          itemAnswers.set(itemId, prev + text);
          setQuestionAnswer(itemId, prev + text);
        },
        onItemDone: (_itemId, item) => {
          const q = item as import("@/types/workflow").QuestionItem;
          setQuestionItem(q.id, withPlatform(q, selectedPlatform));
        },
        onError: (message) => {
          setStatusMessage(message);
        },
      });
    },
    onMutate: () => {
      setIsGeneratingAll(true);
      setStatusMessage("正在批量生成回答...");
    },
    onSuccess: () => {
      const count = useWorkspaceStore.getState().questions.length;
      setStatusMessage(`已完成 ${count} 条回答生成。`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
    onSettled: () => {
      setIsGeneratingAll(false);
    },
  });
```

- [ ] **Step 5: 补充缺少的 import（`useWorkspaceStore` 已有导入，确认无误）**

确认文件顶部已有：
```typescript
import { useWorkspaceStore } from "@/store/workspace-store";
```

- [ ] **Step 6: 类型检查**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace/frontend
bun run typecheck
```

Expected: 无新报错

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/workspace/use-workspace.ts
git commit -m "feat: replace generate/polish mutations with streaming versions"
```

---

### Task 8: 前端 — 对话页面流式展示

**Files:**
- Modify: `frontend/src/features/workspace/chat-message-thread.tsx`
- Modify: `frontend/src/features/workspace/chat-page.tsx`

**Interfaces:**
- Consumes: `streamConversationMessage()` (Task 6)
- Produces: `ChatMessageThread` 新增 `streamingContent?: string` prop，展示流式进行中的消息气泡

- [ ] **Step 1: 修改 `chat-message-thread.tsx`，增加 `streamingContent` prop**

把现有的：
```typescript
type Props = {
  messages: ChatMessage[];
  isLoading: boolean;
  isSending: boolean;
};
```

替换为：
```typescript
type Props = {
  messages: ChatMessage[];
  isLoading: boolean;
  isSending: boolean;
  streamingContent?: string;
};
```

把函数签名中的 `{ messages, isLoading, isSending }` 替换为 `{ messages, isLoading, isSending, streamingContent }`.

在 `{isSending && ...}` 块：

删除：
```tsx
      {isSending && (
        <div className="flex justify-start">
          <div className="rounded-lg bg-muted">
            <ThinkingDots />
          </div>
        </div>
      )}
```

替换为：
```tsx
      {isSending && !streamingContent && (
        <div className="flex justify-start">
          <div className="rounded-lg bg-muted">
            <ThinkingDots />
          </div>
        </div>
      )}
      {isSending && streamingContent && (
        <div className="flex justify-start">
          <div className="w-fit max-w-[75%] rounded-lg px-3 py-2 text-sm leading-relaxed bg-muted text-foreground">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
          </div>
        </div>
      )}
```

- [ ] **Step 2: 修改 `chat-page.tsx` 使用流式端点**

把现有的：
```typescript
  const [isSending, setIsSending] = useState(false);
```

替换为：
```typescript
  const [isSending, setIsSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
```

把 `handleSend` 函数整体替换：

删除：
```typescript
  async function handleSend(message: string) {
    if (!activeSessionId) {
      return;
    }
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setIsSending(true);
    try {
      const res = await sendConversationMessage({ sessionId: activeSessionId, message });
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "发送失败，请重试" }]);
    } finally {
      setIsSending(false);
      queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    }
  }
```

替换为：
```typescript
  async function handleSend(message: string) {
    if (!activeSessionId) {
      return;
    }
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setIsSending(true);
    setStreamingContent("");
    try {
      await streamConversationMessage(
        { sessionId: activeSessionId, message },
        {
          onChunk: (text) => {
            setStreamingContent((prev) => prev + text);
          },
          onDone: (data) => {
            setStreamingContent("");
            setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
          },
          onError: (msg) => {
            setStreamingContent("");
            setMessages((prev) => [...prev, { role: "assistant", content: `发送失败：${msg}` }]);
          },
        },
      );
    } catch {
      setStreamingContent("");
      setMessages((prev) => [...prev, { role: "assistant", content: "发送失败，请重试" }]);
    } finally {
      setIsSending(false);
      queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    }
  }
```

把 `sendConversationMessage` 的 import 替换为 `streamConversationMessage`：

在 import 区域把：
```typescript
import {
  getConversationHistory,
  sendConversationMessage,
} from "./workflow-api";
```

替换为：
```typescript
import {
  getConversationHistory,
  streamConversationMessage,
} from "./workflow-api";
```

在 JSX 中把 `<ChatMessageThread` 的 `isSending={isSending}` 后面加一个 prop：

```tsx
        <ChatMessageThread
          messages={messages}
          isLoading={historyQuery.isLoading}
          isSending={isSending}
          streamingContent={streamingContent}
        />
```

- [ ] **Step 3: 类型检查**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace/frontend
bun run typecheck
```

Expected: 无新报错

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/workspace/chat-message-thread.tsx frontend/src/features/workspace/chat-page.tsx
git commit -m "feat: stream conversation replies in chat page with live typing effect"
```

---

### Task 9: 前端 — 精修聊天和热榜分析改用流式

**Files:**
- Modify: `frontend/src/features/workspace/refinement-chat.tsx`
- Modify: `frontend/src/features/workspace/hotlist-analysis-panel.tsx`

**Interfaces:**
- Consumes: `streamAgentChat()` (Task 6)

- [ ] **Step 1: 修改 `refinement-chat.tsx` 使用流式**

把 import 区域：
```typescript
import { agentChat } from "./workflow-api";
```

替换为：
```typescript
import { streamAgentChat } from "./workflow-api";
```

把 `handleSend` 函数整体替换：

删除：
```typescript
  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    setIsLoading(true);
    setInput("");

    try {
      const res = await agentChat({
        sessionId,
        questionId: question.id,
        message: trimmed,
        currentAnswer: question.answer,
      });

      setLastReply(res.reply);

      if (res.answerUpdated && res.updatedAnswer) {
        updateQuestionAnswer(question.id, res.updatedAnswer);
      }
    } catch {
      setLastReply("请求失败，请重试");
    } finally {
      setIsLoading(false);
    }
  }
```

替换为：
```typescript
  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    setIsLoading(true);
    setInput("");
    setLastReply("");

    try {
      await streamAgentChat(
        {
          sessionId,
          questionId: question.id,
          message: trimmed,
          currentAnswer: question.answer,
        },
        {
          onChunk: (text) => {
            updateQuestionAnswer(question.id, (useWorkspaceStore.getState().questions.find((q) => q.id === question.id)?.answer ?? "") + text);
          },
          onDone: (data) => {
            setLastReply(data.reply);
            if (data.answerUpdated && data.updatedAnswer) {
              updateQuestionAnswer(question.id, data.updatedAnswer);
            }
          },
          onError: (msg) => {
            setLastReply(`请求失败：${msg}`);
          },
        },
      );
    } catch {
      setLastReply("请求失败，请重试");
    } finally {
      setIsLoading(false);
    }
  }
```

在 `refinement-chat.tsx` 的 import 区域加上：
```typescript
import { useWorkspaceStore } from "@/store/workspace-store";
```

- [ ] **Step 2: 修改 `hotlist-analysis-panel.tsx` 使用流式**

把 import 区域：
```typescript
import { agentChat } from "./workflow-api";
```

替换为：
```typescript
import { streamAgentChat } from "./workflow-api";
```

把 `handleAnalyze` 整体替换：

删除：
```typescript
  async function handleAnalyze() {
    setStatus({ type: "loading" });
    try {
      const res = await agentChat({
        sessionId: "hotlist_analysis",
        message: "请分析当前热榜，给出内容策略建议",
      });
      const parsed = parseAnalysisResult(res.reply);
      if (parsed) {
        setStatus({ type: "success", data: parsed });
      } else {
        setStatus({ type: "error", raw: res.reply });
      }
    } catch {
      setStatus({ type: "error", raw: "请求失败，请重试" });
    }
  }
```

替换为：
```typescript
  async function handleAnalyze() {
    setStatus({ type: "loading" });
    try {
      await streamAgentChat(
        {
          sessionId: "hotlist_analysis",
          message: "请分析当前热榜，给出内容策略建议",
        },
        {
          onDone: (data) => {
            const parsed = parseAnalysisResult(data.reply);
            if (parsed) {
              setStatus({ type: "success", data: parsed });
            } else {
              setStatus({ type: "error", raw: data.reply });
            }
          },
          onError: (msg) => {
            setStatus({ type: "error", raw: `请求失败：${msg}` });
          },
        },
      );
    } catch {
      setStatus({ type: "error", raw: "请求失败，请重试" });
    }
  }
```

- [ ] **Step 3: 类型检查**

```bash
cd /Users/lius/Desktop/self/content-answer-workspace/frontend
bun run typecheck
```

Expected: 无新报错

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/workspace/refinement-chat.tsx frontend/src/features/workspace/hotlist-analysis-panel.tsx
git commit -m "feat: stream agent chat replies in refinement and hotlist analysis"
```

---

## 自查清单

- [x] **覆盖率**: `generate_answer`、`polish_answer`、`call_raw`、conversation graph（`chat_node`）全部覆盖
- [x] **兼容性**: 原有 REST 端点全部保留，不影响存量调用
- [x] **SSE 格式**: 统一使用 `data: {JSON}\n\n`，`type` 字段区分事件
- [x] **错误处理**: 每个流式端点和前端回调都有 error 处理
- [x] **增量更新**: `onChunk` 通过 `setQuestionAnswer` 实时更新 store，用户可立即看到生成内容
- [x] **批量生成**: `item_start` / `chunk` / `item_done` 三阶段事件，每条问题独立显示进度
- [x] **对话流式**: `streamingContent` state + `ChatMessageThread` prop 展示打字机效果
- [x] **主题扩展 `expand_topic`**: 不做流式（返回值为 JSON 关键词，非长文本，且是后台采集阶段，用户不直接阅读输出）
