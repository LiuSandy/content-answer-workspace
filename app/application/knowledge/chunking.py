from dataclasses import dataclass, field
import tiktoken


@dataclass
class ChunkResult:
    chunk_type: str  # parent / child
    chunk_index: int
    content: str
    token_count: int
    heading_path: str = ""
    markdown_anchor: str = ""
    parent_index: int | None = None


class MarkdownChunker:
    def __init__(self, parent_max_tokens: int = 1200, child_max_tokens: int = 350, overlap_tokens: int = 50):
        self.parent_max_tokens = parent_max_tokens
        self.child_max_tokens = child_max_tokens
        self.overlap_tokens = overlap_tokens
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None

    def count_tokens(self, text: str) -> int:
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        return len(text) // 4 + 1

    def chunk_markdown(self, markdown: str) -> list[ChunkResult]:
        lines = markdown.splitlines()
        chunks: list[ChunkResult] = []

        # 按 H1/H2 标题或段落拆分为块
        current_heading = ""
        paragraphs: list[str] = []
        current_p: list[str] = []

        for line in lines:
            if line.startswith("#"):
                if current_p:
                    paragraphs.append("\n".join(current_p))
                    current_p = []
                current_heading = line.strip("#").strip()
            elif not line.strip():
                if current_p:
                    paragraphs.append("\n".join(current_p))
                    current_p = []
            else:
                current_p.append(line)

        if current_p:
            paragraphs.append("\n".join(current_p))

        # 构建 Parent Chunks
        parent_idx = 0
        for p in paragraphs:
            if not p.strip():
                continue
            token_cnt = self.count_tokens(p)
            parent_chunk = ChunkResult(
                chunk_type="parent",
                chunk_index=parent_idx,
                content=p,
                token_count=token_cnt,
                heading_path=current_heading,
            )
            chunks.append(parent_chunk)

            # 对该 Parent Chunk 划分 Child Chunks
            child_idx = 0
            words = p.split()
            sub_chunk_content = p if token_cnt <= self.child_max_tokens else " ".join(words[:50])
            child_chunk = ChunkResult(
                chunk_type="child",
                chunk_index=child_idx,
                content=sub_chunk_content,
                token_count=self.count_tokens(sub_chunk_content),
                heading_path=current_heading,
                parent_index=parent_idx,
            )
            chunks.append(child_chunk)
            parent_idx += 1

        return chunks
