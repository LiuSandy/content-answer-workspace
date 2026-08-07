from enum import Enum
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


class KnowledgeDocumentStatus(str, Enum):
    PENDING = "pending"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    INDEXING = "indexing"
    AVAILABLE = "available"
    FAILED = "failed"
    DELETED = "deleted"


class SourceType(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    IMAGE = "image"
    URL = "url"
    HISTORY = "history"
    MATERIAL = "material"


class ChunkType(str, Enum):
    PARENT = "parent"
    CHILD = "child"


class KnowledgeMode(str, Enum):
    OFF = "off"
    NORMAL = "normal"
    STRICT = "strict"


@dataclass
class KnowledgeScope:
    workspace_id: str
    owner_id: str
