"""
Chat Service：管理 Chat 创建、消息存储和 Agent 调用。
路由保持轻薄；采集、生成等编排放在 Service 层。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversation.adapters.db.chats import Chat, Message
from app.modules.acquisition.adapters.db.models import SourceItem, ChatSourceItem
from app.shared.dto import SourceItemDTO


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_chat(self, title: str = "新对话") -> Chat:
        chat = Chat(id=uuid.uuid4(), title=title)
        self._session.add(chat)
        await self._session.commit()
        await self._session.refresh(chat)
        return chat

    async def get_chat(self, chat_id: uuid.UUID) -> Chat | None:
        result = await self._session.execute(select(Chat).where(Chat.id == chat_id))
        return result.scalar_one_or_none()

    async def list_chats(self, limit: int = 50) -> list[Chat]:
        result = await self._session.execute(
            select(Chat).order_by(desc(Chat.updated_at)).limit(limit)
        )
        chats = list(result.scalars().all())
        
        updated = False
        for chat in chats:
            if chat.title == "新对话":
                # 查找当前对话的第一条用户提问
                first_msg_res = await self._session.execute(
                    select(Message)
                    .where(Message.chat_id == chat.id, Message.role == "user")
                    .order_by(Message.created_at)
                    .limit(1)
                )
                first_msg = first_msg_res.scalar_one_or_none()
                if first_msg and first_msg.content:
                    chat.title = first_msg.content[:20]
                    self._session.add(chat)
                    updated = True
        
        if updated:
            await self._session.commit()
            
        return chats

    async def delete_chat(self, chat_id: uuid.UUID) -> bool:
        chat = await self.get_chat(chat_id)
        if not chat:
            return False
        await self._session.delete(chat)
        await self._session.commit()
        return True

    async def save_user_message(
        self,
        chat_id: uuid.UUID,
        content: str,
        parent_message_id: uuid.UUID | None = None,
        run_id: str | None = None,
        message_type: str = "text",
    ) -> Message:
        msg = Message(
            id=uuid.uuid4(),
            chat_id=chat_id,
            role="user",
            message_type=message_type,
            content=content,
            parent_message_id=parent_message_id,
            run_id=run_id,
        )
        self._session.add(msg)
        await self._session.commit()
        await self._session.refresh(msg)
        return msg

    async def save_assistant_message(
        self,
        chat_id: uuid.UUID,
        message_type: str,
        content: str | None,
        payload: dict | None = None,
        parent_message_id: uuid.UUID | None = None,
        run_id: str | None = None,
    ) -> Message:
        msg = Message(
            id=uuid.uuid4(),
            chat_id=chat_id,
            role="assistant",
            message_type=message_type,
            content=content,
            payload=payload,
            parent_message_id=parent_message_id,
            run_id=run_id,
        )
        self._session.add(msg)
        await self._session.commit()
        await self._session.refresh(msg)
        return msg

    async def get_message_path(
        self,
        chat_id: uuid.UUID,
        leaf_message_id: uuid.UUID | None,
    ) -> list[Message]:
        """根据 leaf_message_id 溯源出当前分支完整的历史消息路径列表。
        如果 leaf_message_id 为 None，或在溯源链中遇到 parent_message_id 为 None 且有历史数据，
        我们会采用 created_at 排序作为虚拟父子关系，以确保向后兼容旧的线性消息。
        """
        # 获取该 chat 下所有的消息并按时间排序
        result = await self._session.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
        )
        all_messages = list(result.scalars().all())
        if not all_messages:
            return []

        # 建立 ID 到 Message 的映射
        msg_map = {m.id: m for m in all_messages}

        # 如果未指定 leaf_message_id，则默认选择最后一个消息（线性历史下的最新节点）
        if leaf_message_id is None:
            leaf_message_id = all_messages[-1].id

        path = []
        curr_id = leaf_message_id
        visited = set()

        while curr_id in msg_map and curr_id not in visited:
            visited.add(curr_id)
            msg = msg_map[curr_id]
            path.append(msg)
            if msg.parent_message_id is not None:
                curr_id = msg.parent_message_id
            else:
                # 虚拟时间序列关联兜底：
                # 如果 parent_message_id 为 None，且在该消息前还有更早的消息，则关联到前一个消息
                try:
                    idx = all_messages.index(msg)
                    if idx > 0:
                        curr_id = all_messages[idx - 1].id
                    else:
                        break
                except ValueError:
                    break

        path.reverse()
        return path

    async def get_messages(self, chat_id: uuid.UUID, limit: int = 100) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def save_source_items(
        self,
        chat_id: uuid.UUID,
        items: list[SourceItemDTO],
    ) -> list[SourceItem]:
        """去重并保存 SourceItem；已存在的帖子不重复写入，只建立关联。"""
        saved: list[SourceItem] = []
        for dto in items:
            # 尝试按去重键查找已有记录
            existing = None
            if dto.external_id:
                result = await self._session.execute(
                    select(SourceItem).where(
                        SourceItem.platform == dto.platform,
                        SourceItem.external_id == dto.external_id,
                    )
                )
                existing = result.scalar_one_or_none()

            if existing is None:
                # 新建记录
                source_item = SourceItem(
                    id=uuid.uuid4(),
                    platform=dto.platform,
                    external_id=dto.external_id,
                    url=dto.url,
                    title=dto.title,
                    content=dto.content,
                    author=dto.author,
                    summary=dto.summary,
                    metrics=dto.metrics or {},
                    raw_metadata=dto.raw_metadata or {},
                    published_at=dto.published_at,
                )
                self._session.add(source_item)
                await self._session.flush()
                saved.append(source_item)
            else:
                saved.append(existing)

            # 建立 chat-source_item 关联（如果还没有）
            link_result = await self._session.execute(
                select(ChatSourceItem).where(
                    ChatSourceItem.chat_id == chat_id,
                    ChatSourceItem.source_item_id == saved[-1].id,
                )
            )
            if link_result.scalar_one_or_none() is None:
                link = ChatSourceItem(
                    chat_id=chat_id,
                    source_item_id=saved[-1].id,
                    display_order=len(saved),
                )
                self._session.add(link)

        await self._session.commit()
        return saved

    async def get_source_items_for_chat(self, chat_id: uuid.UUID) -> list[SourceItem]:
        result = await self._session.execute(
            select(SourceItem)
            .join(ChatSourceItem, ChatSourceItem.source_item_id == SourceItem.id)
            .where(ChatSourceItem.chat_id == chat_id)
            .order_by(ChatSourceItem.display_order)
        )
        return list(result.scalars().all())
