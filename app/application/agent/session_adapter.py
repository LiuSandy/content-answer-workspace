from __future__ import annotations


class InMemorySessionAdapter:
    """每请求一个实例，持有该请求内的 session 答案状态，避免跨请求共享状态。"""

    def __init__(self, initial_answers: dict[tuple[str, str], str] | None = None) -> None:
        self._store: dict[tuple[str, str], str] = initial_answers or {}

    async def get_answer(self, session_id: str, question_id: str) -> str:
        return self._store.get((session_id, question_id), "")

    async def update_answer(self, session_id: str, question_id: str, content: str) -> None:
        self._store[(session_id, question_id)] = content

    def get_updated_answer(self, session_id: str, question_id: str) -> str | None:
        return self._store.get((session_id, question_id))
