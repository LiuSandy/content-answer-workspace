"""Bounded, persistence-free review loop for newly generated content."""
from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.shared.dto import QualityReport
from app.shared.errors import LLMOutputError
from .review import ReviewContext

QUALITY_THRESHOLD = 75
MAX_CREATION_ROUNDS = 3

ReviewFn = Callable[[str, ReviewContext], Awaitable[QualityReport]]
RewriteFn = Callable[[str, str], Awaitable[str]]


@dataclass(frozen=True)
class CreationReviewRound:
    iteration: int
    content: str
    report: QualityReport


@dataclass(frozen=True)
class CreationReviewOutcome:
    final_content: str
    final_report: QualityReport | None
    iterations: int
    passed: bool
    selected_iteration: int
    rounds: Sequence[CreationReviewRound]
    review_failed: bool = False
    error_message: str | None = None


@dataclass(frozen=True)
class CreationReviewEvent:
    name: str
    data: dict[str, Any]
    outcome: CreationReviewOutcome | None = None


def _outcome_event(outcome: CreationReviewOutcome) -> CreationReviewEvent:
    return CreationReviewEvent(
        name="creation_review.outcome",
        data={},
        outcome=outcome,
    )


async def run_creation_review(
    initial_content: str,
    context: ReviewContext,
    evaluate: ReviewFn,
    rewrite: RewriteFn,
) -> AsyncIterator[CreationReviewEvent]:
    """Review and selectively rewrite an internal draft up to 20 times.

    The generator has no persistence side effects. Only ``LLMOutputError`` is
    converted into a failed outcome; cancellation and programming errors remain
    visible to the caller.
    """
    current_content = initial_content
    rounds: list[CreationReviewRound] = []

    for iteration in range(1, MAX_CREATION_ROUNDS + 1):
        round_context = dataclasses.replace(
            context,
            iteration=iteration,
            previous_review=(
                rounds[-1].report.model_dump(mode="json", by_alias=True)
                if rounds
                else None
            ),
        )
        yield CreationReviewEvent(
            "review.started",
            {
                "iteration": iteration,
                "maxIterations": MAX_CREATION_ROUNDS,
            },
        )

        try:
            report = await evaluate(current_content, round_context)
            passed = report.overall_score >= QUALITY_THRESHOLD
            rounds.append(CreationReviewRound(iteration, current_content, report))
            yield CreationReviewEvent(
                "review.completed",
                {
                    "iteration": iteration,
                    "overallScore": report.overall_score,
                    "passed": passed,
                },
            )

            if passed:
                yield _outcome_event(
                    CreationReviewOutcome(
                        final_content=current_content,
                        final_report=report,
                        iterations=iteration,
                        passed=True,
                        selected_iteration=iteration,
                        rounds=tuple(rounds),
                    )
                )
                return

            if iteration < MAX_CREATION_ROUNDS:
                instruction = (report.rewrite_instruction or "").strip()
                if not instruction:
                    raise LLMOutputError("质检未通过但未提供重写指令")
                yield CreationReviewEvent(
                    "rewrite.started",
                    {
                        "iteration": iteration + 1,
                        "maxIterations": MAX_CREATION_ROUNDS,
                    },
                )
                current_content = await rewrite(current_content, instruction)
        except LLMOutputError as exc:
            yield _outcome_event(
                CreationReviewOutcome(
                    final_content=current_content,
                    # The current draft did not receive a valid report. A score
                    # from an earlier draft must not be attached to it.
                    final_report=None,
                    iterations=iteration,
                    passed=False,
                    selected_iteration=iteration,
                    rounds=tuple(rounds),
                    review_failed=True,
                    error_message=str(exc),
                )
            )
            return

    selected_round = max(
        rounds,
        key=lambda round_: (round_.report.overall_score, round_.iteration),
    )
    yield _outcome_event(
        CreationReviewOutcome(
            final_content=selected_round.content,
            final_report=selected_round.report,
            iterations=MAX_CREATION_ROUNDS,
            passed=False,
            selected_iteration=selected_round.iteration,
            rounds=tuple(rounds),
        )
    )
