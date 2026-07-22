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


def test_auto_migrate_with_simulated_legacy_sql(tmp_path):
    flag_file = tmp_path / ".migration_completed"
    
    # 模拟旧物理备份文件存在
    backup_file = tmp_path / "old_data_backup.sql"
    mock_sql = (
        "INSERT INTO chats (id, title) VALUES ('00000000-0000-0000-0000-000000000001', '测试历史对话');\n"
        "INSERT INTO messages (id, chat_id, role, content) VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'user', '你好');\n"
        "INSERT INTO questions (id, title) VALUES ('00000000-0000-0000-0000-000000000003', '测试问题');\n"
    )
    backup_file.write_text(mock_sql, encoding="utf-8")

    # 执行首次无感缝合检测
    result_first = auto_migrate_if_needed(flag_file=flag_file)
    assert flag_file.exists()

    # 幂等性二次测试（秒级跳过）
    result_second = auto_migrate_if_needed(flag_file=flag_file)
    assert result_second == {"chats": 0, "messages": 0, "questions": 0, "answers": 0}
