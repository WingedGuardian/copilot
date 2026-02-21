"""Navigator duo: adversarial review loop for task quality assurance.

The navigator is a thinking-model peer that reviews the orchestrator's work
at two checkpoints:
  1. Plan review (1 round) — after task decomposition, before execution
  2. Execution review (up to max_rounds) — when orchestrator finishes or blocks

Design decisions:
  - Navigator uses provider.chat() directly (no tools, no agent loop)
  - Parse failure = escalate to user (fail safe, never silently approve)
  - Two-tier loop protection: max_duo_rounds per cycle + max_review_cycles per task
  - Sycophancy detection lives in the dream cycle, not here (cross-task concern)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from loguru import logger


@dataclass
class NavigatorVerdict:
    """Result of a single navigator review round."""
    approved: bool
    needs_user: bool
    critique: str
    themes: list[str]


@dataclass
class DuoMetrics:
    """Accumulated metrics for a single task's duo interactions."""
    plan_review_rounds: int = 0
    plan_approved_first_try: bool = False
    review_cycles: int = 0
    total_rounds: int = 0
    disagreement_themes: list[str] = field(default_factory=list)
    resolution_pattern: str = ""
    navigator_model: str = ""
    navigator_cost_usd: float = 0.0

    def to_json(self) -> str:
        return json.dumps({
            "plan_review_rounds": self.plan_review_rounds,
            "plan_approved_first_try": self.plan_approved_first_try,
            "review_cycles": self.review_cycles,
            "total_rounds": self.total_rounds,
            "disagreement_themes": self.disagreement_themes,
            "resolution_pattern": self.resolution_pattern,
            "navigator_model": self.navigator_model,
            "navigator_cost_usd": self.navigator_cost_usd,
        })

    @classmethod
    def from_json(cls, text: str) -> DuoMetrics:
        try:
            data = json.loads(text)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()


def parse_navigator_response(text: str) -> NavigatorVerdict:
    from nanobot.copilot.dream.cycle import DreamCycle
    parsed = DreamCycle._parse_llm_json(text)
    if not isinstance(parsed, dict):
        logger.warning("Navigator response parse failed, escalating to user")
        return NavigatorVerdict(
            approved=False, needs_user=True,
            critique=f"Navigator response could not be parsed: {(text or '')[:200]}",
            themes=["parse_failure"],
        )
    return NavigatorVerdict(
        approved=bool(parsed.get("approved", False)),
        needs_user=bool(parsed.get("needs_user", False)),
        critique=str(parsed.get("critique", "")),
        themes=parsed.get("themes", []) if isinstance(parsed.get("themes"), list) else [],
    )


_NAVIGATOR_RESPONSE_FORMAT = """\
You MUST respond with ONLY valid JSON in this exact format:
{"approved": true/false, "needs_user": true/false, "critique": "specific actionable text", "themes": ["theme1", "theme2"]}

Rules:
- "approved": true only if the work meets your standards. Do NOT approve out of politeness.
- "needs_user": true if you and the orchestrator genuinely cannot resolve this without human input.
- "critique": explain WHY something passes or fails. "Looks good" is not valid.
- "themes": 1-3 word labels categorizing your concerns (e.g., "error_handling", "missing_validation").
"""


def build_plan_review_prompt(
    task_title: str, task_description: str, steps: list[dict], navigator_identity: str,
) -> list[dict]:
    system = navigator_identity or "You are a critical reviewer in an AI duo."
    system += "\n\n## Your Task\nReview the proposed execution plan. Check for:\n"
    system += "- Step sufficiency: do the steps actually accomplish the task?\n"
    system += "- Step ordering: are dependencies correct?\n"
    system += "- Missing steps: anything critical omitted?\n"
    system += "- Model assignment: are recommended models appropriate for each step?\n"
    system += f"\n{_NAVIGATOR_RESPONSE_FORMAT}"

    steps_text = "\n".join(
        f"  {i+1}. [{s.get('tool_type', 'general')}] {s.get('description', '')}"
        f"{' (model: ' + s['recommended_model'] + ')' if s.get('recommended_model') else ''}"
        for i, s in enumerate(steps)
    )
    user = (
        f"## Task: {task_title}\n{task_description}\n\n"
        f"## Proposed Steps\n{steps_text}\n\n"
        f"Review this plan. Is it sufficient and well-ordered to accomplish the task?"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_execution_review_prompt(
    task_title: str, task_description: str, steps_with_results: list[dict],
    current_output: str, prior_critiques: list[str], navigator_identity: str,
) -> list[dict]:
    system = navigator_identity or "You are a critical reviewer in an AI duo."
    system += "\n\n## Your Task\nReview the orchestrator's completed work. Check for:\n"
    system += "- Task fulfillment: does the output actually accomplish what was requested?\n"
    system += "- Quality: is the work thorough, correct, and complete?\n"
    system += "- Edge cases: are there obvious gaps or failure modes?\n"
    system += "- You have limited rounds. Be thorough in each review.\n"
    system += f"\n{_NAVIGATOR_RESPONSE_FORMAT}"

    steps_text = "\n".join(
        f"  {i+1}. [{s.get('status', '?')}] {s.get('description', '')}"
        f"\n     Result: {(s.get('result', '') or '')[:200]}"
        for i, s in enumerate(steps_with_results)
    )
    user = (
        f"## Task: {task_title}\n{task_description}\n\n"
        f"## Execution Steps & Results\n{steps_text}\n\n"
        f"## Current Output\n{current_output[:3000]}\n"
    )
    if prior_critiques:
        critique_text = "\n".join(f"- Round {i+1}: {c}" for i, c in enumerate(prior_critiques))
        user += (
            f"\n## Prior Critiques (you raised these earlier — the orchestrator revised)\n"
            f"{critique_text}\n\nHas the orchestrator adequately addressed your concerns?"
        )
    else:
        user += "\nIs this work complete and of sufficient quality?"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def review_plan(
    steps: list[dict], task: Any,
    navigator_fn: Callable[[list[dict]], Awaitable[str]], identity: str,
) -> tuple[NavigatorVerdict, int]:
    messages = build_plan_review_prompt(
        task_title=task.title, task_description=task.description or task.title,
        steps=steps, navigator_identity=identity,
    )
    try:
        response = await navigator_fn(messages)
        verdict = parse_navigator_response(response)
    except Exception as e:
        logger.error(f"Navigator plan review failed: {e}")
        verdict = NavigatorVerdict(
            approved=True, needs_user=False,
            critique=f"Navigator unavailable: {e}", themes=["navigator_error"],
        )
    logger.info(
        f"Navigator plan review: approved={verdict.approved}, "
        f"needs_user={verdict.needs_user}, themes={verdict.themes}"
    )
    return verdict, 1


async def review_execution(
    task: Any, steps_with_results: list[dict], current_output: str,
    navigator_fn: Callable[[list[dict]], Awaitable[str]],
    revise_fn: Callable[[str], Awaitable[str]], identity: str,
    max_rounds: int = 3, metrics: DuoMetrics | None = None,
) -> tuple[NavigatorVerdict, str, DuoMetrics]:
    if metrics is None:
        metrics = DuoMetrics()
    prior_critiques: list[str] = []
    output = current_output

    for round_num in range(1, max_rounds + 1):
        messages = build_execution_review_prompt(
            task_title=task.title, task_description=task.description or task.title,
            steps_with_results=steps_with_results, current_output=output,
            prior_critiques=prior_critiques, navigator_identity=identity,
        )
        try:
            response = await navigator_fn(messages)
            verdict = parse_navigator_response(response)
        except Exception as e:
            logger.error(f"Navigator execution review round {round_num} failed: {e}")
            verdict = NavigatorVerdict(
                approved=False, needs_user=True,
                critique=f"Navigator unavailable: {e}", themes=["navigator_error"],
            )
        metrics.total_rounds += 1
        metrics.disagreement_themes.extend(verdict.themes)
        logger.info(
            f"Navigator execution review round {round_num}/{max_rounds}: "
            f"approved={verdict.approved}, needs_user={verdict.needs_user}, themes={verdict.themes}"
        )
        if verdict.approved:
            metrics.resolution_pattern = "converged"
            return verdict, output, metrics
        if verdict.needs_user:
            metrics.resolution_pattern = "user_escalation"
            return verdict, output, metrics
        prior_critiques.append(verdict.critique)
        revision_prompt = (
            f"The navigator reviewed your work and has concerns:\n\n"
            f"{verdict.critique}\n\n"
            f"Please revise your output to address these concerns. "
            f"Focus specifically on: {', '.join(verdict.themes) if verdict.themes else 'the issues raised'}."
        )
        try:
            output = await revise_fn(revision_prompt)
        except Exception as e:
            logger.error(f"Orchestrator revision failed: {e}")
            metrics.resolution_pattern = "user_escalation"
            return NavigatorVerdict(
                approved=False, needs_user=True,
                critique=f"Revision failed: {e}", themes=["revision_error"],
            ), output, metrics

    metrics.resolution_pattern = "max_rounds"
    final_verdict = NavigatorVerdict(
        approved=False, needs_user=True,
        critique=f"Max review rounds ({max_rounds}) exhausted. Last concerns: {prior_critiques[-1] if prior_critiques else 'unknown'}",
        themes=["max_rounds_exhausted"],
    )
    return final_verdict, output, metrics
