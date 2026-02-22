"""Prompt templates for task lifecycle operations."""

from __future__ import annotations


def build_decomposition_prompt(
    task_description: str,
    clarifying_context: str | None = None,
    model_pool: str | None = None,
    past_wisdom: str | None = None,
) -> str:
    """Build a prompt for the frontier model to decompose a task into steps."""
    context_block = ""
    if clarifying_context:
        context_block = f"\n## Additional Context\n{clarifying_context}\n"

    model_block = ""
    if model_pool:
        model_block = f"\n## Available Models\n{model_pool}\n"

    wisdom_block = ""
    if past_wisdom:
        wisdom_block = (
            "\n## Execution Wisdom from Past Similar Tasks\n"
            f"{past_wisdom}\n"
            "Consider these learnings when planning.\n"
        )

    return f"""You are a task decomposition agent. Break down the following task into concrete, actionable steps.

## Task
{task_description}
{context_block}{model_block}{wisdom_block}
## Instructions
1. Break the task into 2-8 sequential steps
2. Each step should be independently executable
3. Assign a tool_type to each step:
   - "research" — web search, reading, information gathering
   - "write" — creating text content, formatting, documents
   - "shell" — running commands, file operations
   - "code" — writing/modifying code
   - "general" — anything else
4. For each step, recommend a model from the Available Models list based on the step's requirements. Use the model's API identifier. Leave empty for default routing.
5. If you need more information to properly decompose the task, return clarifying_questions instead of steps

## Response Format (JSON only)
{{
  "steps": [
    {{"description": "Step description", "tool_type": "research|write|shell|code|general", "recommended_model": "api/model-id or empty"}}
  ],
  "clarifying_questions": ["question1", "question2"]
}}

Return ONLY valid JSON. No markdown fences, no explanation."""


def build_progress_message(
    task_id: str,
    task_title: str,
    completed_steps: list[dict],
    current_step: dict | None = None,
    questions: list[str] | None = None,
) -> str:
    """Build a progress notification message for WhatsApp."""
    lines = [f"Task #{task_id}: {task_title}"]

    for step in completed_steps:
        lines.append(f"  done: {step['description']}")

    if current_step:
        lines.append(f"  >> {current_step['description']}")

    if questions:
        lines.append("")
        for q in questions:
            lines.append(f"  ? {q}")

    return "\n".join(lines)


def build_navigator_escalation_message(
    task_id: str,
    task_title: str,
    critique: str,
    resolution_pattern: str,
) -> str:
    """Build a notification for navigator escalations that need user attention."""
    header = f"Task #{task_id}: {task_title}"
    if resolution_pattern == "plan_review":
        label = "Navigator flagged plan for review"
    elif resolution_pattern == "max_cycles":
        label = "Navigator: max review cycles reached"
    elif resolution_pattern == "max_rounds":
        label = "Navigator: max rounds exhausted"
    elif resolution_pattern == "user_escalation":
        label = "Navigator + orchestrator: need your input"
    else:
        label = "Navigator review"
    return f"{header}\n  {label}:\n  {critique}"
