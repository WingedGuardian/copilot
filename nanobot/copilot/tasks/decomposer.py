"""Task decomposition: LLM response parser."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class DecompositionResult:
    """Result of decomposing a task into steps."""
    steps: list[dict] = field(default_factory=list)
    clarifying_questions: list[str] = field(default_factory=list)
    error: str | None = None


def parse_decomposition_response(raw: str) -> DecompositionResult:
    """Parse the LLM's decomposition response into structured data."""
    text = raw.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Decomposition parse failed: {e}")
        return DecompositionResult(error=f"Invalid JSON: {e}")

    steps = data.get("steps", [])
    questions = data.get("clarifying_questions", [])

    # Validate steps have required fields
    valid_steps = []
    for step in steps:
        if isinstance(step, dict) and "description" in step:
            valid_steps.append({
                "description": step["description"],
                "tool_type": step.get("tool_type", "general"),
            })

    return DecompositionResult(steps=valid_steps, clarifying_questions=questions)
