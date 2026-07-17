import uuid
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.persistence import Base
from app.persistence.models.chats import Chat, Message
from app.application.chat_service import ChatService

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
