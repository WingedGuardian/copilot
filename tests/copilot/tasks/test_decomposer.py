"""Tests for task decomposition parser and prompts."""

import json

from nanobot.copilot.tasks.decomposer import parse_decomposition_response
from nanobot.copilot.tasks.prompts import build_decomposition_prompt


def test_parse_valid_decomposition():
    raw = json.dumps({
        "steps": [
            {"description": "Search for VPS providers", "tool_type": "research"},
            {"description": "Compare pricing tiers", "tool_type": "research"},
            {"description": "Format comparison table", "tool_type": "write"},
        ],
        "clarifying_questions": [],
    })
    result = parse_decomposition_response(raw)
    assert len(result.steps) == 3
    assert result.steps[0]["tool_type"] == "research"
    assert result.clarifying_questions == []
    assert result.error is None


def test_parse_with_markdown_fences():
    raw = '```json\n{"steps": [{"description": "Do thing", "tool_type": "general"}], "clarifying_questions": []}\n```'
    result = parse_decomposition_response(raw)
    assert len(result.steps) == 1


def test_parse_with_questions():
    raw = json.dumps({
        "steps": [],
        "clarifying_questions": ["What budget range?", "Which region?"],
    })
    result = parse_decomposition_response(raw)
    assert len(result.steps) == 0
    assert len(result.clarifying_questions) == 2


def test_parse_invalid_json():
    result = parse_decomposition_response("this is not json")
    assert len(result.steps) == 0
    assert result.error is not None


def test_parse_missing_tool_type_defaults_to_general():
    raw = json.dumps({"steps": [{"description": "Do thing"}], "clarifying_questions": []})
    result = parse_decomposition_response(raw)
    assert result.steps[0]["tool_type"] == "general"


def test_build_prompt_contains_task():
    prompt = build_decomposition_prompt("Research VPS providers under $20")
    assert "Research VPS providers under $20" in prompt
    assert "tool_type" in prompt


def test_build_prompt_with_context():
    prompt = build_decomposition_prompt(
        "Build a landing page",
        clarifying_context="Target audience: developers. Style: minimal.",
    )
    assert "developers" in prompt
    assert "minimal" in prompt
