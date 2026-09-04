import asyncio

import pytest

from app.modules.writing.application.review import ReviewContext
from app.modules.writing.application.creation_review import run_creation_review
from app.shared.dto import QualityReport
from app.shared.errors import LLMOutputError


def report(score: int, instruction: str = "继续定向修改") -> QualityReport:
    return QualityReport(
        overall_score=score,
        dimension_scores={
            "relevance": score,
            "information_density": score,
            "readability": score,
            "logic_coherence": score,
            "word_count_compliance": score,
        },
        issues=[],
        suggestions=[],
        rewrite_instruction=None if score >= 75 else instruction,
        summary="测试评审",
    )


def context() -> ReviewContext:
    return ReviewContext("问题", None, 1000, 1)


@pytest.mark.asyncio
async def test_first_round_passes_without_rewrite():
    evaluated_contexts: list[ReviewContext] = []

    async def evaluate(content: str, review_context: ReviewContext):
        assert content == "draft-1"
        evaluated_contexts.append(review_context)
        return report(75)

    async def rewrite(content: str, instruction: str):
        pytest.fail("达标内容不应重写")

    events = [
        event
        async for event in run_creation_review(
            initial_content="draft-1",
            context=context(),
            evaluate=evaluate,
            rewrite=rewrite,
        )
    ]

    assert [event.name for event in events] == [
        "review.started",
        "review.completed",
        "creation_review.outcome",
    ]
    assert evaluated_contexts[0].iteration == 1
    assert evaluated_contexts[0].previous_review is None
    outcome = events[-1].outcome
    assert outcome is not None
    assert outcome.final_content == "draft-1"
    assert outcome.final_report == report(75)
    assert outcome.iterations == 1
    assert outcome.passed is True
    assert outcome.selected_iteration == 1
    assert outcome.review_failed is False


@pytest.mark.asyncio
async def test_second_round_passes_with_previous_review_context():
    reports = iter([report(70, "补充论据"), report(80)])
    evaluated_contexts: list[ReviewContext] = []
    rewrite_calls: list[tuple[str, str]] = []

    async def evaluate(content: str, review_context: ReviewContext):
        evaluated_contexts.append(review_context)
        return next(reports)

    async def rewrite(content: str, instruction: str):
        rewrite_calls.append((content, instruction))
        return "draft-2"

    events = [
        event
        async for event in run_creation_review(
            initial_content="draft-1",
            context=context(),
            evaluate=evaluate,
            rewrite=rewrite,
        )
    ]

    assert [event.name for event in events[:-1]] == [
        "review.started",
        "review.completed",
        "rewrite.started",
        "review.started",
        "review.completed",
    ]
    assert rewrite_calls == [("draft-1", "补充论据")]
    rewrite_event = next(event for event in events if event.name == "rewrite.started")
    assert rewrite_event.data == {"iteration": 2, "maxIterations": 3}
    assert evaluated_contexts[1].iteration == 2
    assert evaluated_contexts[1].previous_review is not None
    assert evaluated_contexts[1].previous_review["overallScore"] == 70
    outcome = events[-1].outcome
    assert outcome is not None
    assert outcome.final_content == "draft-2"
    assert outcome.iterations == 2
    assert outcome.passed is True
    assert outcome.selected_iteration == 2


@pytest.mark.asyncio
async def test_three_failed_rounds_choose_highest_score_and_latest_on_tie():
    reports = iter([report(70), report(72), report(72)])

    async def evaluate(content: str, review_context: ReviewContext):
        return next(reports)

    async def rewrite(content: str, instruction: str):
        current = int(content.removeprefix("draft-"))
        return f"draft-{current + 1}"

    events = [
        event
        async for event in run_creation_review(
            initial_content="draft-1",
            context=context(),
            evaluate=evaluate,
            rewrite=rewrite,
        )
    ]
    outcome = events[-1].outcome

    assert outcome is not None
    assert outcome.iterations == 3
    assert outcome.passed is False
    assert outcome.selected_iteration == 3
    assert outcome.final_content == "draft-3"
    assert outcome.final_report == report(72)
    assert [round_.iteration for round_ in outcome.rounds] == list(range(1, 4))


@pytest.mark.asyncio
async def test_llm_output_error_preserves_current_draft_without_fake_score():
    calls = 0

    async def evaluate(content: str, review_context: ReviewContext):
        nonlocal calls
        calls += 1
        if calls == 1:
            return report(60, "定向重写")
        raise LLMOutputError("结构化输出失败")

    async def rewrite(content: str, instruction: str):
        assert (content, instruction) == ("current-draft", "定向重写")
        return "rewritten-current-draft"

    events = [
        event
        async for event in run_creation_review(
            initial_content="current-draft",
            context=context(),
            evaluate=evaluate,
            rewrite=rewrite,
        )
    ]

    assert [event.name for event in events] == [
        "review.started",
        "review.completed",
        "rewrite.started",
        "review.started",
        "creation_review.outcome",
    ]
    completed = [event for event in events if event.name == "review.completed"]
    assert [event.data["overallScore"] for event in completed] == [60]
    outcome = events[-1].outcome
    assert outcome is not None
    assert outcome.final_content == "rewritten-current-draft"
    assert outcome.final_report is None
    assert outcome.iterations == 2
    assert outcome.passed is False
    assert outcome.selected_iteration == 2
    assert len(outcome.rounds) == 1
    assert outcome.rounds[0].report.overall_score == 60
    assert outcome.review_failed is True
    assert outcome.error_message == "结构化输出失败"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.CancelledError(), RuntimeError("bug")])
async def test_does_not_swallow_cancellation_or_unknown_errors(error: BaseException):
    async def evaluate(content: str, review_context: ReviewContext):
        raise error

    async def rewrite(content: str, instruction: str):
        pytest.fail("异常后不应重写")

    with pytest.raises(type(error), match=None if isinstance(error, asyncio.CancelledError) else "bug"):
        async for _ in run_creation_review(
            initial_content="draft-1",
            context=context(),
            evaluate=evaluate,
            rewrite=rewrite,
        ):
            pass
