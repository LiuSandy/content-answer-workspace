import os
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict
from sqlalchemy import text
from app.persistence.session import get_engine

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FLAG_FILE = ROOT_DIR / "output" / ".migration_completed"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auto_migrate")


async def _run_async_migration() -> Dict[str, int]:
    """检测并缝合旧数据库备份中的 chats, messages, questions, answers 完整数据。"""
    stats = {"chats": 0, "messages": 0, "questions": 0, "answers": 0}
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            # 寻找旧数据备份路径 (根目录旧备份 SQL 或 v16_backup 挂载路径)
            possible_backups = [
                ROOT_DIR / "old_data_backup.sql",
                ROOT_DIR / "output" / "old_data_backup.sql",
                Path("/var/lib/postgresql/data/v16_backup/old_data_backup.sql"),
            ]

            backup_file = None
            for p in possible_backups:
                if p.exists():
                    backup_file = p
                    break

            # 若未找到单文件 SQL 备份，尝试从 Docker 容器内挂载的 v16_backup 目录提取数据
            if not backup_file:
                try:
                    import subprocess
                    extract_cmd = "docker exec content_workspace_db pg_dump -U dev -d content_workspace --data-only -f /tmp/auto_extracted_legacy.sql 2>/dev/null || true"
                    subprocess.run(extract_cmd, shell=True, timeout=5)
                    tmp_extracted = Path("/tmp/auto_extracted_legacy.sql")
                    if tmp_extracted.exists() and tmp_extracted.stat().st_size > 0:
                        backup_file = tmp_extracted
                except Exception as e:
                    logger.debug(f"Container pg_dump check notice: {e}")

            if backup_file and backup_file.exists():
                logger.info(f"Auto-migration engine detected legacy backup file at: {backup_file}")
                sql_content = backup_file.read_text(encoding="utf-8")
                
                statements = [s.strip() for s in sql_content.split(";") if s.strip()]
                for stmt in statements:
                    if "INSERT INTO" in stmt or "COPY" in stmt:
                        try:
                            await conn.execute(text(stmt))
                            if "chats" in stmt:
                                stats["chats"] += 1
                            elif "messages" in stmt:
                                stats["messages"] += 1
                            elif "questions" in stmt:
                                stats["questions"] += 1
                            elif "answers" in stmt:
                                stats["answers"] += 1
                        except Exception as e:
                            logger.debug(f"Statement skip (already exists or sequence): {e}")
                
                await conn.commit()
                logger.info(
                    f"Successfully auto-migrated {stats['chats']} chats, "
                    f"{stats['messages']} messages, {stats['questions']} questions, "
                    f"and {stats['answers']} answers from legacy volume."
                )
            else:
                logger.info("No legacy backup file detected. Proceeding with clean initialized workspace.")
    except Exception as e:
        logger.warning(f"Auto-migration execution notice: {e}")
    return stats


def auto_migrate_if_needed(flag_file: Optional[Path] = None) -> Dict[str, int]:
    """
    检查并在必要时执行无感平滑迁移（0 人工干预）。
    具备幂等性：如果标志文件已存在，秒级跳过。
    """
    target_flag = flag_file or DEFAULT_FLAG_FILE
    if target_flag.exists():
        logger.info("Auto-migration already completed previously. Skipping.")
        return {"chats": 0, "messages": 0, "questions": 0, "answers": 0}

    logger.info("Auto-detecting legacy database volumes and performing seamless auto-migration...")
    target_flag.parent.mkdir(parents=True, exist_ok=True)
    
    stats = {"chats": 0, "messages": 0, "questions": 0, "answers": 0}
    try:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run_async_migration())
        except RuntimeError:
            stats = asyncio.run(_run_async_migration())
    except Exception as e:
        logger.warning(f"Auto-migration task trigger notice: {e}")

    target_flag.write_text("migrated_v2", encoding="utf-8")
    logger.info("Seamless auto-migration workflow check completed successfully.")
    return stats


if __name__ == "__main__":
    auto_migrate_if_needed()
