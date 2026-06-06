from __future__ import annotations

from .core.config import (
    COOKIE_PATH_DEFAULT,
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
from .services.answer_service import generate_answer, get_openai_client
from .services.session_service import read_latest_session, save_workflow_result
from .services.zhihu_service import (
    build_keyword_hints,
    clean_text,
    collect_questions,
    fetch_question_details,
    fetch_zhihu_results_for_topic,
    get_topic_preview,
    get_zhihu_question_web_url,
    map_search_item,
    parse_json_response,
    question_matches_keyword,
    to_iso_time,
    unique_by,
)


async def run_workflow(options: dict | None = None):
    options = options or {}
    collected = await collect_questions(options)
    config = collected.config
    if options.get("skipAnswerGeneration") is True or config.skip_answer_generation:
        return collected

    answered_items = []
    for item in collected.items:
        answer = await generate_answer(item, config.answer_style, config.cta_text, config.system_prompt)
        answered_items.append(item.model_copy(update={"answer": answer}))

    return collected.model_copy(update={"items": answered_items})
