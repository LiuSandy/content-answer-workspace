from __future__ import annotations

import os
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID


SOURCE_FILE_STATES = ("pending", "processing", "recognized", "archived", "failed")


class SourceFileStorage:
    """源文件状态目录；只接受根目录内的普通文件。"""

    def __init__(self, root: Path):
        self.root = root.resolve()
        for state in SOURCE_FILE_STATES:
            (self.root / state).mkdir(parents=True, exist_ok=True)

    def state_dir(self, state: str) -> Path:
        if state not in SOURCE_FILE_STATES:
            raise ValueError(f"Unknown source file state: {state}")
        return self.root / state

    def resolve_relative(self, relative_path: str | Path) -> Path:
        path = (self.root / Path(relative_path)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Source file path escapes configured root")
        return path

    def iter_pending(self) -> list[Path]:
        pending = self.state_dir("pending")
        files: list[Path] = []
        for path in pending.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.name.startswith(".") or path.suffix.lower() in {".uploading", ".tmp", ".part"}:
                continue
            files.append(path)
        return sorted(files)

    def pending_relative(self, path: Path) -> Path:
        resolved = path.resolve()
        pending = self.state_dir("pending")
        if not resolved.is_relative_to(pending):
            raise ValueError("File is not under pending directory")
        return resolved.relative_to(pending)

    def save_upload(self, filename: str, content: bytes) -> Path:
        safe_name = Path(filename).name or "uploaded_file"
        pending = self.state_dir("pending")
        target = self._available_target(pending / safe_name, None)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.uploading")
        temporary.write_bytes(content)
        os.replace(temporary, target)
        return target

    async def save_upload_stream(
        self,
        filename: str,
        upload: Any,
        max_bytes: int,
        buffer_bytes: int,
    ) -> tuple[Path, int, str]:
        """固定缓冲区接收上传并原子发布到 pending，返回路径、大小和 SHA-256。"""
        safe_name = Path(filename).name or "uploaded_file"
        target = self._available_target(self.state_dir("pending") / safe_name, None)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.uploading")
        digest = hashlib.sha256()
        total = 0
        try:
            with temporary.open("wb") as handle:
                while True:
                    chunk = await upload.read(buffer_bytes)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("file_too_large")
                    handle.write(chunk)
                    digest.update(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target, total, digest.hexdigest()

    @staticmethod
    def stream_sha256(path: Path, buffer_bytes: int) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(buffer_bytes):
                digest.update(chunk)
        return digest.hexdigest()

    def move(self, current_relative_path: str | Path, target_state: str, source_id: UUID | None) -> Path:
        source = self.resolve_relative(current_relative_path)
        if not source.exists() or not source.is_file() or source.is_symlink():
            raise FileNotFoundError(str(source))
        parts = Path(current_relative_path).parts
        relative_inside_state = Path(*parts[1:]) if parts and parts[0] in SOURCE_FILE_STATES else Path(source.name)
        target = self._available_target(self.state_dir(target_state) / relative_inside_state, source_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)
        return target.relative_to(self.root)

    @staticmethod
    def _available_target(target: Path, source_id: UUID | None) -> Path:
        if not target.exists():
            return target
        suffix = f"--{str(source_id)[:8]}" if source_id else "--copy"
        candidate = target.with_name(f"{target.stem}{suffix}{target.suffix}")
        counter = 2
        while candidate.exists():
            candidate = target.with_name(f"{target.stem}{suffix}-{counter}{target.suffix}")
            counter += 1
        return candidate
