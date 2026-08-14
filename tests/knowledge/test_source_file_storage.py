from pathlib import Path
from uuid import uuid4

import pytest

from app.infrastructure.files.source_files import SourceFileStorage


class _Upload:
    def __init__(self, content: bytes):
        self.content = content
        self.offset = 0

    async def read(self, size: int) -> bytes:
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_source_file_storage_preserves_relative_directories(tmp_path: Path):
    storage = SourceFileStorage(tmp_path / "source-files")
    pending = storage.state_dir("pending") / "技术资料" / "算法.pdf"
    pending.parent.mkdir(parents=True)
    pending.write_bytes(b"pdf")

    moved = storage.move("pending/技术资料/算法.pdf", "processing", uuid4())

    assert moved == Path("processing/技术资料/算法.pdf")
    assert storage.resolve_relative(moved).read_bytes() == b"pdf"
    assert not pending.exists()


def test_source_file_storage_never_overwrites_target(tmp_path: Path):
    storage = SourceFileStorage(tmp_path / "source-files")
    source_id = uuid4()
    pending = storage.state_dir("pending") / "same.txt"
    pending.write_text("new", encoding="utf-8")
    existing = storage.state_dir("failed") / "same.txt"
    existing.write_text("old", encoding="utf-8")

    moved = storage.move("pending/same.txt", "failed", source_id)

    assert existing.read_text(encoding="utf-8") == "old"
    assert str(source_id)[:8] in moved.name
    assert storage.resolve_relative(moved).read_text(encoding="utf-8") == "new"


def test_source_file_storage_rejects_path_escape_and_symlink(tmp_path: Path):
    storage = SourceFileStorage(tmp_path / "source-files")
    with pytest.raises(ValueError):
        storage.resolve_relative("../../secret")

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = storage.state_dir("pending") / "link.txt"
    link.symlink_to(outside)
    assert storage.iter_pending() == []


@pytest.mark.asyncio
async def test_upload_stream_writes_in_chunks_and_computes_hash(tmp_path: Path):
    import hashlib

    storage = SourceFileStorage(tmp_path / "source-files")
    content = b"0123456789" * 100
    path, size, digest = await storage.save_upload_stream(
        "large.pdf", _Upload(content), max_bytes=2000, buffer_bytes=17
    )

    assert size == len(content)
    assert digest == hashlib.sha256(content).hexdigest()
    assert path.read_bytes() == content
    assert not list(storage.state_dir("pending").glob("*.uploading"))


@pytest.mark.asyncio
async def test_upload_stream_rejects_oversized_file_without_partial_output(tmp_path: Path):
    storage = SourceFileStorage(tmp_path / "source-files")
    with pytest.raises(ValueError, match="file_too_large"):
        await storage.save_upload_stream(
            "too-large.pdf", _Upload(b"x" * 20), max_bytes=10, buffer_bytes=4
        )
    assert storage.iter_pending() == []
