from pathlib import Path
from uuid import uuid4
import hashlib
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


def test_publish_markdown_from_file_streams_and_hashes_utf8(tmp_path: Path):
    storage = KnowledgeStorage(tmp_path / "sources", tmp_path / "documents")
    source = tmp_path / "large.md"
    content = ("标题 🌏\n" + "正文内容\n" * 100).encode("utf-8")
    source.write_bytes(content)

    document_id = uuid4()
    active_path, content_hash = storage.publish_markdown_from_file(
        document_id, source, buffer_bytes=5
    )

    assert active_path.read_bytes() == content
    assert content_hash == hashlib.sha256(content).hexdigest()


def test_publish_markdown_from_file_replaces_invalid_utf8_like_previous_behavior(tmp_path: Path):
    storage = KnowledgeStorage(tmp_path / "sources", tmp_path / "documents")
    source = tmp_path / "invalid.md"
    source.write_bytes(b"prefix\xffsuffix")

    active_path, content_hash = storage.publish_markdown_from_file(
        uuid4(), source, buffer_bytes=1
    )

    expected = "prefix\ufffdsuffix".encode("utf-8")
    assert active_path.read_bytes() == expected
    assert content_hash == hashlib.sha256(expected).hexdigest()
