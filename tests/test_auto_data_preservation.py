import os
import shutil
from pathlib import Path
import pytest
from app.core.db_guard import create_db_snapshot, check_db_health
from scripts.auto_migrate_db import auto_migrate_if_needed


def test_db_guard_snapshot_creation(tmp_path):
    backup_dir = tmp_path / "backups"
    snapshot_file = create_db_snapshot(backup_dir=backup_dir)
    assert snapshot_file.exists()
    assert snapshot_file.name.startswith("db_snapshot_")


def test_auto_migrate_idempotency(tmp_path):
    flag_file = tmp_path / ".migration_completed"
    # 首次执行
    result = auto_migrate_if_needed(flag_file=flag_file)
    assert result is True
    assert flag_file.exists()

    # 再次执行（幂等性校验，秒级跳过）
    result_again = auto_migrate_if_needed(flag_file=flag_file)
    assert result_again is False
