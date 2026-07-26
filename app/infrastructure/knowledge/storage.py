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

    def read_source(self, source_path: str | Path) -> bytes | None:
        """读取已落盘的原始上传文件；供重新解析（reconvert）使用。

        校验路径必须位于 sources_dir 之内——source_path 来自数据库，
        若被篡改成任意路径不应导致越权读取。
        """
        target_path = Path(source_path).resolve()
        if not target_path.is_relative_to(self.sources_dir):
            raise ValueError(f"Source path escapes sources dir: {source_path}")
        if not target_path.exists():
            return None
        return target_path.read_bytes()

    def compute_hash(self, content: bytes | str) -> str:
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()
