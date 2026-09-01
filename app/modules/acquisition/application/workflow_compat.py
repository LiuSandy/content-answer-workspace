from __future__ import annotations

from .workflow import WorkflowService
from app.platform.config.runtime import (
    COOKIE_PATH_DEFAULT,
    DEFAULT_PLATFORM,
    ENV_PATH,
    OUTPUT_DIR,
    ROOT_DIR,
    get_default_topics,
    get_required_env,
    get_workflow_config,
    is_truthy,
    load_env_file,
    parse_positive_int,
)
from app.modules.writing.application.answer_service import generate_answer
from app.modules.documents.application.sessions import read_latest_session, save_workflow_result
from .zhihu import (
    build_keyword_hints,
    clean_text,
    collect_questions,
    fetch_question_details,
    fetch_zhihu_results_for_topic,
    get_topic_preview,
    get_zhihu_question_web_url,
    map_search_item,
    question_matches_keyword,
    to_iso_time,
    unique_by,
)

workflow_service = WorkflowService()


async def run_workflow(options: dict | None = None):
    """运行兼容旧入口的完整工作流；这样旧代码可以继续调用 run_workflow，同时实际逻辑交给新服务。"""

    return await workflow_service.run(options)
