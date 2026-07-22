from pathlib import Path
from uuid import UUID
import hashlib


class KnowledgeStorage:
    def __init__(self, sources_dir: Path, documents_dir: Path):
        self.sources_dir = sources_dir.resolve()
        self.documents_dir = documents_dir.resolve()
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir.mkdir(parents=True, exist_ok=True)

    def save_source(self, document_id: UUID, filename: str, content: bytes) -> Path:
        doc_dir = self.sources_dir / str(document_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = Path(filename).name
        target_path = doc_dir / safe_filename
        target_path.write_bytes(content)
        return target_path

    def save_candidate(self, document_id: UUID, markdown: str) -> Path:
        target_path = self.documents_dir / f"{document_id}.candidate.md"
        target_path.write_text(markdown, encoding="utf-8")
        return target_path

    def publish_markdown(self, document_id: UUID, markdown: str) -> Path:
        target_path = self.documents_dir / f"{document_id}.md"
        target_path.write_text(markdown, encoding="utf-8")
        # 清理已有的候选稿
        candidate_path = self.documents_dir / f"{document_id}.candidate.md"
        if candidate_path.exists():
            candidate_path.unlink()
        return target_path

    def read_markdown(self, document_id: UUID, is_candidate: bool = False) -> str | None:
        filename = f"{document_id}.candidate.md" if is_candidate else f"{document_id}.md"
        target_path = self.documents_dir / filename
        if not target_path.exists():
            return None
        return target_path.read_text(encoding="utf-8")

    def compute_hash(self, content: bytes | str) -> str:
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()
