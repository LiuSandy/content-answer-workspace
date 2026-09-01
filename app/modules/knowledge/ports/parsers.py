"""Document parsing boundary owned by Knowledge."""

from typing import Any, Protocol


class DocumentParserPort(Protocol):
    async def parse(self, content: bytes, **metadata: Any) -> Any: ...
