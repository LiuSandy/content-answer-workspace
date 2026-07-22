from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextBlock:
    doc_title: str
    content: str
    source_type: str
    source_url: str | None = None
    updated_at: str | None = None


class ContextBuilder:
    def __init__(self, max_tokens: int = 6000):
        self.max_tokens = max_tokens

    def build_context(self, blocks: list[ContextBlock]) -> tuple[str, list[dict[str, Any]]]:
        context_parts = []
        sources = []

        for idx, block in enumerate(blocks, start=1):
            label = f"[S{idx}]"
            part = f"{label} Source: {block.doc_title}\n{block.content}\n"
            context_parts.append(part)
            sources.append({
                "label": label,
                "title": block.doc_title,
                "sourceType": block.source_type,
                "sourceUrl": block.source_url,
                "contentSnippet": block.content[:150],
            })

        full_context = "\n".join(context_parts)
        return full_context, sources
