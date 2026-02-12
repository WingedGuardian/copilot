"""Deterministic routing heuristics — no LLM classification call."""

import re
from dataclasses import dataclass


@dataclass
class RouteDecision:
    """Result of routing classification."""

    target: str  # "local", "fast", "big"
    reason: str  # Why this route was chosen
    model: str   # Specific model identifier to use


# Explicit user intent to upgrade to the big model.
_UPGRADE_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"\b(?:think\s+(?:hard|deeply|carefully|about this)"
        r"|brainstorm|deep\s+dive|take\s+your\s+time"
        r"|really\s+think|think\s+this\s+through"
        r"|analyze\s+(?:carefully|in\s+depth|thoroughly)"
        r"|this\s+is\s+(?:important|critical|complex|tricky)"
        r"|need\s+(?:your\s+best|a\s+good|careful|thorough)"
        r"|go\s+(?:deep|all\s+out)"
        r"|let(?:'?s)?\s+get\s+(?:serious|creative))\b",
        re.I,
    ),
    re.compile(
        r"\b(?:use\s+(?:the\s+)?(?:big|powerful|strong|cloud|best)\s+model"
        r"|use\s+(?:sonnet|claude|gpt[- ]?4))\b",
        re.I,
    ),
]

# Explicit user intent to downgrade to local/fast (keep it cheap & quick).
_DOWNGRADE_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"\b(?:quick\s+question|just\s+(?:a\s+)?quick|real\s+quick"
        r"|simple\s+question|nothing\s+fancy|keep\s+it\s+simple"
        r"|don'?t\s+overthink"
        r"|use\s+(?:the\s+)?(?:local|small|fast|cheap)\s+model)\b",
        re.I,
    ),
]

# Patterns that indicate complex tasks needing a stronger model.
_COMPLEXITY_PATTERNS: list[re.Pattern] = [
    re.compile(r"```"),                          # Code blocks
    re.compile(r"(?:first|step\s*1).*(?:then|next|step\s*2)", re.I | re.S),  # Multi-step
    re.compile(
        r"\b(?:debug|refactor|architect|optimize|kubernetes|k8s|docker"
        r"|terraform|ansible|sql|migration|deploy|pipeline|ci/cd"
        r"|security|penetration|exploit|vulnerability)\b",
        re.I,
    ),
]


def classify(
    message_text: str,
    has_images: bool,
    token_count: int,
    lessons: list[dict] | None = None,
    *,
    local_model: str = "qwen2.5-14b-instruct",
    fast_model: str = "anthropic/claude-3-haiku-20240307",
    big_model: str = "anthropic/claude-sonnet-4-20250514",
) -> RouteDecision:
    """Classify a message and decide which model tier to use.

    Rules are evaluated first-match-wins:
      1. Images → big (local models can't process images)
      2. Input > 4096 chars → big (long input needs strong model)
      3. Explicit user upgrade intent → big
      4. Explicit user downgrade intent → local
      5. Conversation tokens > 3000 → fast (save context budget on cloud)
      6. High-confidence lesson override → per lesson
      7. Keyword/pattern complexity → big
      8. Default → local
    """
    # 1. Images
    if has_images:
        return RouteDecision("big", "images", big_model)

    # 2. Long input
    if len(message_text) > 4096:
        return RouteDecision("big", "overflow", big_model)

    # 3. Explicit upgrade — user wants the big model
    for pattern in _UPGRADE_PATTERNS:
        if pattern.search(message_text):
            return RouteDecision("big", "user_upgrade", big_model)

    # 4. Explicit downgrade — user wants local/fast
    for pattern in _DOWNGRADE_PATTERNS:
        if pattern.search(message_text):
            return RouteDecision("local", "user_downgrade", local_model)

    # 5. High token accumulation
    if token_count > 3000:
        return RouteDecision("fast", "token_accumulation", fast_model)

    # 6. Lesson overrides
    if lessons:
        for lesson in lessons:
            confidence = lesson.get("confidence", 0)
            if confidence >= 0.70:
                target = lesson.get("route_target", "big")
                model = {
                    "local": local_model,
                    "fast": fast_model,
                    "big": big_model,
                }.get(target, big_model)
                return RouteDecision(target, "lesson", model)

    # 7. Complexity heuristics
    for pattern in _COMPLEXITY_PATTERNS:
        if pattern.search(message_text):
            return RouteDecision("big", "complexity", big_model)

    # 8. Default → local
    return RouteDecision("local", "default", local_model)
