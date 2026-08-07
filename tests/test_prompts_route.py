from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.server import app
from app.prompts.registry import prompt_registry, warmup


@pytest.fixture(autouse=True)
def setup_prompts_registry(tmp_path: Path):
    # 创建临时 prompts 目录以供测试，防污染真实文件
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # model_profiles.yml
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
content: "样式规范文字"
""", encoding="utf-8")

    # 平台包（content-only 片段格式）
    platforms_dir = prompts_dir / "platforms"
    platforms_dir.mkdir()
    (platforms_dir / "zhihu.yml").write_text("""
id: platform.zhihu
version: "1.0.0"
content: "知乎平台创作规范初始内容"
""", encoding="utf-8")

    # answer_generate
    writing_dir = prompts_dir / "writing"
    writing_dir.mkdir()
    prompt_file = writing_dir / "answer_generate.yml"
    prompt_file.write_text("""
id: writing.answer_generate
version: "1.0.0"
variables:
  required:
    - title
    - content
    - platform
includes:
  style_rules: shared.style_rules
messages:
  - role: system
    content: "初始测试系统提示词: {{ style_rules }}"
  - role: user
    content: "初始用户提示词"
""", encoding="utf-8")

    # 重置全局单例的状态以防止多用例重复加载冲突
    prompt_registry._frozen = False
    prompt_registry._prompts.clear()
    prompt_registry._sources.clear()

    # 初始化测试用的 Registry 实例，注意 freeze=False 允许测试中重载
    warmup(prompts_dir, freeze=False)
    yield

    # 清理以防影响其他测试文件
    prompt_registry._frozen = False
    prompt_registry._prompts.clear()
    prompt_registry._sources.clear()


def test_get_prompt_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/prompts/writing.answer_generate")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["id"] == "writing.answer_generate"
    assert "初始测试系统提示词" in data["data"]["systemPrompt"]
    assert "初始用户提示词" in data["data"]["userPrompt"]


def test_get_prompt_endpoint_not_found() -> None:
    client = TestClient(app)
    response = client.get("/api/prompts/non_existent_id")
    assert response.status_code == 404


def test_update_prompt_endpoint_success() -> None:
    client = TestClient(app)
    response = client.put(
        "/api/prompts/writing.answer_generate",
        json={
            "systemPrompt": "更新后的系统提示词: {{ style_rules }}",
            "userPrompt": ""
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # 验证 Registry 的内存状态是否已被实时刷新重载
    rendered = prompt_registry.render(
        "writing.answer_generate",
        title="t",
        content="c",
        platform="p",
    )
    assert "更新后的系统提示词" in rendered.messages[0].content


def test_get_fragment_prompt_endpoint() -> None:
    # 平台包是 content-only 片段格式，应以 kind=fragment 返回 content 内容
    client = TestClient(app)
    response = client.get("/api/prompts/platform.zhihu")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["kind"] == "fragment"
    assert "知乎平台创作规范初始内容" in data["data"]["systemPrompt"]


def test_update_fragment_prompt_endpoint() -> None:
    client = TestClient(app)
    response = client.put(
        "/api/prompts/platform.zhihu",
        json={"systemPrompt": "更新后的知乎平台规范", "userPrompt": ""},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # 验证 Registry 内存状态已刷新，render_fragment 立即拿到新内容
    assert "更新后的知乎平台规范" in prompt_registry.render_fragment("platform.zhihu")


def test_update_prompt_endpoint_invalid_payload() -> None:
    client = TestClient(app)
    # 缺少必填的 systemPrompt 字段，触发校验报错
    response = client.put(
        "/api/prompts/writing.answer_generate",
        json={"userPrompt": "用户提示词"},
    )
    # FastAPI returns 422 for pydantic validation errors by default
    assert response.status_code == 422


def test_update_prompt_preserves_user_message_and_variables() -> None:
    """更新提示词后 user message 与 variables 必须保留，不能被覆盖或清空。"""
    client = TestClient(app)
    response = client.put(
        "/api/prompts/writing.answer_generate",
        json={
            "systemPrompt": "更新后的系统提示词: {{ style_rules }}",
            "userPrompt": "",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # 直接从磁盘读取 YAML，验证 user message 与 variables 均被保留
    from pathlib import Path
    import yaml
    file_path = prompt_registry.get_source_path("writing.answer_generate")
    raw = yaml.safe_load(Path(file_path).read_text(encoding="utf-8"))
    messages = raw.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assert user_msgs, "user message 不应被删除"
    assert user_msgs[0]["content"] == "初始用户提示词"
    variables = raw.get("variables", {})
    required = variables.get("required", [])
    assert "title" in required
    assert "content" in required
    assert "platform" in required


def test_update_prompt_with_user_prompt_updates_user_message() -> None:
    """当请求携带 userPrompt 时，应更新 user 消息内容而不是删除它。"""
    client = TestClient(app)
    response = client.put(
        "/api/prompts/writing.answer_generate",
        json={
            "systemPrompt": "更新后的系统提示词: {{ style_rules }}",
            "userPrompt": "新的用户提示词",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    from pathlib import Path
    import yaml
    file_path = prompt_registry.get_source_path("writing.answer_generate")
    raw = yaml.safe_load(Path(file_path).read_text(encoding="utf-8"))
    messages = raw.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assert user_msgs
    assert user_msgs[0]["content"] == "新的用户提示词"
    # variables 依然保留
    variables = raw.get("variables", {})
    assert "title" in variables.get("required", [])
