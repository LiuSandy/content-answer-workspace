from pathlib import Path
from uuid import uuid4
import pytest
from app.modules.knowledge.adapters.db.storage import KnowledgeStorage


def test_knowledge_storage_paths(tmp_path: Path):
    sources_dir = tmp_path / "sources"
    documents_dir = tmp_path / "documents"
    storage = KnowledgeStorage(sources_dir=sources_dir, documents_dir=documents_dir)

    doc_id = uuid4()
    source_path = storage.save_source(doc_id, "example.pdf", b"PDF content")
    assert source_path.exists()
    assert str(source_path).startswith(str(sources_dir))

    candidate_path = storage.save_candidate(doc_id, "# Candidate MD")
    assert candidate_path.exists()
    assert str(candidate_path).startswith(str(documents_dir))

    active_path = storage.publish_markdown(doc_id, "# Active MD")
    assert active_path.exists()
    assert active_path.read_text(encoding="utf-8") == "# Active MD"
