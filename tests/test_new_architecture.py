"""测试新架构核心组件：Prompt Registry 渲染、Document 乐观并发锁、选区合并与错误。"""
from __future__ import annotations

import uuid
import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.prompts.registry import PromptRegistry, RenderedPrompt
from app.prompts.errors import PromptVariableMissingError, PromptNotFoundError
from app.errors import DocumentConflictError, ValidationError
from app.persistence import Base
from app.persistence.models.content import SourceItem
from app.application.document_service import DocumentService
from app.domain.dto import SelectionDTO


# ── SQLite 兼容 JSONB 编译规则 ────────────────────────────────────────────────
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"  # SQLite and aiosqlite will store JSON as text


# ── Prompt Registry 测试 ──────────────────────────────────────────────────────

def test_prompt_registry_load_and_render(tmp_path: Path) -> None:
    # 1. 创建临时 Prompt YAML 文件
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # model_profiles
    (prompts_dir / "model_profiles.yml").write_text("""
model_profiles:
  default:
    provider: deepseek
    model: deepseek-chat
    temperature: 0.7
    max_tokens: 4096
""", encoding="utf-8")

    # style_rules
    shared_dir = prompts_dir / "shared"
    shared_dir.mkdir()
    (shared_dir / "style_rules.yml").write_text("""
id: shared.style_rules
version: "1.0.0"
content: |
  格式要求：
  - 加粗重点
""", encoding="utf-8")

    # answer_generate
    writing_dir = prompts_dir / "writing"
    writing_dir.mkdir()
    (writing_dir / "answer_generate.yml").write_text("""
id: writing.answer_generate
version: "1.0.0"
variables:
  required:
    - title
    - content
includes:
  style_rules: shared.style_rules
messages:
  - role: system
    content: |
      你是个创作者。
      {{ style_rules }}
  - role: user
    content: |
      标题：{{ title }}
      内容：{{ content }}
""", encoding="utf-8")

    # 2. 初始化 Registry
    registry = PromptRegistry()
    registry.load_from_dir(prompts_dir)
    
    assert "writing.answer_generate" in registry.list_ids()
    assert "shared.style_rules" in registry.list_ids()

    # 3. 正常渲染
    rendered = registry.render(
        "writing.answer_generate",
        title="测试标题",
        content="测试内容"
    )
    assert rendered.prompt_id == "writing.answer_generate"
    assert rendered.model == "deepseek-v4-pro"
    assert rendered.temperature == 0.7
    assert rendered.max_tokens == 4096
    
    # 验证 includes 展开和 variables 替换
    system_msg = rendered.messages[0].content
    user_msg = rendered.messages[1].content
    assert "格式要求：" in system_msg
    assert "- 加粗重点" in system_msg
    assert "标题：测试标题" in user_msg
    assert "内容：测试内容" in user_msg

    # 4. 缺少必填变量渲染报错
    with pytest.raises(PromptVariableMissingError) as exc_info:
        registry.render("writing.answer_generate", title="测试标题")
    assert "content" in exc_info.value.missing

    # 5. 未找到 prompt 报错
    with pytest.raises(PromptNotFoundError):
        registry.get("non_existent")


# ── DB & DocumentService 乐观锁测试 ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_document_service_optimistic_locking() -> None:
    # 1. 创建内存 SQLite 数据库用于测试（使用 SQL 模拟，需要 sqlalchemy.ext.asyncio)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # 初始化表结构
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with session_factory() as session:
        # 创建 SourceItem 作为外键关联对象
        source_item = SourceItem(
            id=uuid.uuid4(),
            platform="zhihu",
            url="https://zhihu.com/question/123",
            title="测试标题",
        )
        session.add(source_item)
        await session.commit()

        doc_service = DocumentService(session)
        # 初始化 Document
        doc = await doc_service.get_or_create_document(source_item.id)
        assert doc.lock_version == 1
        assert doc.current_content is None

        # 2. 正常修改（预期版本号一致，修改成功后自增）
        doc = await doc_service.update_content(
            document_id=doc.id,
            content="第一次修改内容",
            expected_lock_version=1,
        )
        assert doc.lock_version == 2
        assert doc.current_content == "第一次修改内容"

        # 3. 乐观锁冲突测试（传入过期版本号 1，预期报错）
        with pytest.raises(DocumentConflictError) as exc_info:
            await doc_service.update_content(
                document_id=doc.id,
                content="过期修改内容",
                expected_lock_version=1,
            )
        assert exc_info.value.expected == 1
        assert exc_info.value.actual == 2

        # 再次修改成功（传入当前最新版本号 2）
        doc = await doc_service.update_content(
            document_id=doc.id,
            content="第二次修改内容",
            expected_lock_version=2,
        )
        assert doc.lock_version == 3

    await engine.dispose()
