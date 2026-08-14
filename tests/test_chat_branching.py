import uuid
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.database import Base
from app.infrastructure.database.models.chats import Chat, Message
from app.services.chat_service import ChatService

# SQLite compatible JSONB compilation rule
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

@pytest.mark.asyncio
async def test_chat_message_branching_path() -> None:
    # 1. Setup in-memory SQLite database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with session_factory() as session:
        chat_service = ChatService(session)
        
        # 2. Create Chat
        chat = await chat_service.create_chat("Test Chat Branching")
        chat_id = chat.id

        # 3. Save Message 1 (User) -> Message 2 (Assistant)
        u1 = await chat_service.save_user_message(chat_id, "User Q1", parent_message_id=None)
        a1 = await chat_service.save_assistant_message(chat_id, "text", "Assistant A1", parent_message_id=u1.id)

        # 4. Branch 1: User Q2 -> Assistant A2 (child of Assistant A1)
        u2 = await chat_service.save_user_message(chat_id, "User Q2 Branch A", parent_message_id=a1.id)
        a2 = await chat_service.save_assistant_message(chat_id, "text", "Assistant A2 Branch A", parent_message_id=u2.id)

        # 5. Branch 2: User Q3 -> Assistant A3 (child of Assistant A1 - Sibling to Q2 Branch A)
        u3 = await chat_service.save_user_message(chat_id, "User Q3 Branch B", parent_message_id=a1.id)
        a3 = await chat_service.save_assistant_message(chat_id, "text", "Assistant A3 Branch B", parent_message_id=u3.id)

        # 6. Verify get_message_path for Branch 1 (leaf is a2.id)
        path1 = await chat_service.get_message_path(chat_id, a2.id)
        assert len(path1) == 4
        assert path1[0].id == u1.id
        assert path1[1].id == a1.id
        assert path1[2].id == u2.id
        assert path1[3].id == a2.id

        # 7. Verify get_message_path for Branch 2 (leaf is a3.id)
        path2 = await chat_service.get_message_path(chat_id, a3.id)
        assert len(path2) == 4
        assert path2[0].id == u1.id
        assert path2[1].id == a1.id
        assert path2[2].id == u3.id
        assert path2[3].id == a3.id

        # 8. Verify fallback behavior when leaf_message_id is None
        # It defaults to the newest message (a3.id) as the leaf, and returns its branch path
        path_fallback = await chat_service.get_message_path(chat_id, None)
        assert len(path_fallback) == 4
        assert path_fallback[0].id == u1.id
        assert path_fallback[1].id == a1.id
        assert path_fallback[2].id == u3.id
        assert path_fallback[3].id == a3.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_branching_current_user_message_not_duplicated() -> None:
    """每次图运行输入中当前用户消息只出现一次。

    当 leaf_message_id 为 None（首次提问或线性历史）时，get_message_path 会把
    最新消息（即刚保存的当前用户消息）当作叶子，历史路径因此会包含它；拼装
    LangGraph 输入时必须排除该条当前消息，只保留历史，再额外追加一次当前消息。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        chat_service = ChatService(session)
        chat = await chat_service.create_chat("Dedup")

        # 第一轮：保存当前用户消息（无 parent），路径会包含它自身
        u1 = await chat_service.save_user_message(chat.id, "User Q1", parent_message_id=None)
        a1 = await chat_service.save_assistant_message(chat.id, "text", "Assistant A1", parent_message_id=u1.id)

        # 第二轮：新的用户消息
        u2 = await chat_service.save_user_message(chat.id, "User Q2", parent_message_id=a1.id)

        # 历史路径（到 a1 为止，不含 u2）
        path_hist = await chat_service.get_message_path(chat.id, a1.id)
        assert [m.id for m in path_hist] == [u1.id, a1.id]

        # 用 ChatService 相同逻辑拼装 LangGraph 输入：历史 + 当前用户消息
        # 必须排除刚保存的当前用户消息（u2 不应出现在历史里）
        from app.api.routes.chats import build_langgraph_history

        history = build_langgraph_history(path_hist, str(u2.id))
        langgraph_messages = history + [{"role": "user", "content": "User Q2"}]
        # 当前用户消息 "User Q2" 只能出现一次（历史排除后由调用方追加一次）
        current_msgs = [m for m in langgraph_messages if m["content"] == "User Q2"]
        assert len(current_msgs) == 1
        # 历史中不应包含当前用户消息 u2
        assert all(m["content"] != "User Q2" for m in history)
        # 历史仍包含上一轮的用户消息（合法历史，不算重复）
        assert any(m["content"] == "User Q1" for m in history)

    await engine.dispose()
