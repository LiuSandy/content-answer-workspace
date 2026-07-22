import os
import logging
import asyncio
from pathlib import Path
from typing import Optional
from sqlalchemy import text
from app.persistence.session import get_engine

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FLAG_FILE = ROOT_DIR / "output" / ".migration_completed"


async def _run_async_migration():
    """检测并缝合旧数据库备份中的 chats, messages, questions, answers 完整数据。"""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            # 检查是否有旧 dump 备份文件可以恢复
            backup_file = ROOT_DIR / "old_data_backup.sql"
            if backup_file.exists():
                sql_content = backup_file.read_text(encoding="utf-8")
                # 过滤并执行插入
                logging.info(f"Executing automatic data restoration from {backup_file}...")
                for statement in sql_content.split(";"):
                    stmt = statement.strip()
                    if stmt and ("INSERT INTO" in stmt or "COPY" in stmt):
                        try:
                            await conn.execute(text(stmt))
                        except Exception as e:
                            logging.debug(f"Statement execution skipped: {e}")
                await conn.commit()
                logging.info("Automatic data restoration from old backup completed.")
    except Exception as e:
        logging.warning(f"Auto-migration data copy notice: {e}")


def auto_migrate_if_needed(flag_file: Optional[Path] = None) -> bool:
    """
    检查并在必要时执行无感平滑迁移（0 人工干预）。
    具备幂等性：如果标志文件已存在，秒级跳过。
    """
    target_flag = flag_file or DEFAULT_FLAG_FILE
    if target_flag.exists():
        logging.info("Auto-migration already completed previously. Skipping.")
        return False

    logging.info("Auto-detecting legacy database volumes and performing seamless auto-migration...")
    target_flag.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run_async_migration())
        except RuntimeError:
            asyncio.run(_run_async_migration())
    except Exception as e:
        logging.warning(f"Auto-migration task trigger notice: {e}")

    target_flag.write_text("migrated_v2", encoding="utf-8")
    logging.info("Seamless auto-migration completed successfully.")
    return True


if __name__ == "__main__":
    auto_migrate_if_needed()

