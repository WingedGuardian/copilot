"""Tests for Navigator duo: response parsing, plan review, execution review."""

import asyncio
import json

from nanobot.copilot.tasks.navigator import (
    DuoMetrics,
    NavigatorVerdict,
    parse_navigator_response,
    review_execution,
    review_plan,
)


def test_parse_navigator_response_valid_json():
    raw = json.dumps({
        "approved": True, "needs_user": False,
        "critique": "Steps are well-ordered and complete.", "themes": ["sufficient"],
    })
    v = parse_navigator_response(raw)
    assert v.approved is True
    assert v.needs_user is False
    assert v.themes == ["sufficient"]


def test_parse_navigator_response_markdown_fenced():
    raw = '```json\n{"approved": false, "needs_user": true, "critique": "Missing validation", "themes": ["validation"]}\n```'
    v = parse_navigator_response(raw)
    assert v.approved is False
    assert v.needs_user is True


def test_parse_navigator_response_malformed():
    v = parse_navigator_response("This is not JSON at all.")
    assert v.approved is False
    assert v.needs_user is True
    assert "parse_failure" in v.themes


def test_parse_navigator_response_empty():
    v = parse_navigator_response("")
    assert v.approved is False
    assert v.needs_user is True


def test_duo_metrics_round_trip():
    m = DuoMetrics(total_rounds=5, disagreement_themes=["error_handling", "validation"], resolution_pattern="converged")
    m2 = DuoMetrics.from_json(m.to_json())
    assert m2.total_rounds == 5
    assert m2.disagreement_themes == ["error_handling", "validation"]


def test_duo_metrics_from_invalid_json():
    m = DuoMetrics.from_json("not json")
    assert m.total_rounds == 0


class _FakeTask:
    def __init__(self):
        self.id = "t-001"
        self.title = "Test task"
        self.description = "Do something"
        self.step_count = 0
        self.session_key = "task:t-001"
        self.steps = []
        self.status = "active"


def test_plan_review_approved():
    async def _run():
        async def nav_fn(messages):
            return json.dumps({"approved": True, "needs_user": False, "critique": "Good plan.", "themes": []})
        steps = [{"description": "Step 1", "tool_type": "research"}]
        verdict, rounds = await review_plan(steps, _FakeTask(), nav_fn, "")
        assert verdict.approved is True
        assert rounds == 1
    asyncio.get_event_loop().run_until_complete(_run())


def test_plan_review_needs_user():
    async def _run():
        async def nav_fn(messages):
            return json.dumps({"approved": False, "needs_user": True, "critique": "Steps are too vague.", "themes": ["clarity"]})
        steps = [{"description": "Do stuff", "tool_type": "general"}]
        verdict, _ = await review_plan(steps, _FakeTask(), nav_fn, "")
        assert verdict.needs_user is True
    asyncio.get_event_loop().run_until_complete(_run())


def test_execution_review_first_round_approval():
    async def _run():
        async def nav_fn(messages):
            return json.dumps({"approved": True, "needs_user": False, "critique": "Complete.", "themes": []})
        async def revise_fn(prompt):
            return "revised"
        steps = [{"description": "Step 1", "status": "completed", "result": "done"}]
        verdict, output, metrics = await review_execution(_FakeTask(), steps, "output", nav_fn, revise_fn, "", max_rounds=3)
        assert verdict.approved is True
        assert metrics.resolution_pattern == "converged"
    asyncio.get_event_loop().run_until_complete(_run())


def test_execution_review_revision_then_approval():
    async def _run():
        call_count = 0
        async def nav_fn(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"approved": False, "needs_user": False, "critique": "Missing error handling.", "themes": ["error_handling"]})
            return json.dumps({"approved": True, "needs_user": False, "critique": "Fixed.", "themes": []})
        async def revise_fn(prompt):
            return "revised with error handling"
        steps = [{"description": "Step 1", "status": "completed", "result": "done"}]
        verdict, output, metrics = await review_execution(_FakeTask(), steps, "initial", nav_fn, revise_fn, "", max_rounds=3)
        assert verdict.approved is True
        assert metrics.total_rounds == 2
        assert "error_handling" in metrics.disagreement_themes
    asyncio.get_event_loop().run_until_complete(_run())


def test_execution_review_max_rounds_exhausted():
    async def _run():
        async def nav_fn(messages):
            return json.dumps({"approved": False, "needs_user": False, "critique": "Not good enough.", "themes": ["quality"]})
        async def revise_fn(prompt):
            return "another attempt"
        steps = [{"description": "Step 1", "status": "completed", "result": "done"}]
        verdict, output, metrics = await review_execution(_FakeTask(), steps, "initial", nav_fn, revise_fn, "", max_rounds=3)
        assert verdict.needs_user is True
        assert metrics.resolution_pattern == "max_rounds"
    asyncio.get_event_loop().run_until_complete(_run())


def test_duo_metrics_accumulation():
    async def _run():
        round_num = 0
        async def nav_fn(messages):
            nonlocal round_num
            round_num += 1
            if round_num <= 2:
                return json.dumps({"approved": False, "needs_user": False, "critique": f"Issue {round_num}", "themes": [f"theme_{round_num}"]})
            return json.dumps({"approved": True, "needs_user": False, "critique": "All resolved.", "themes": []})
        async def revise_fn(prompt):
            return f"revision {round_num}"
        metrics = DuoMetrics(plan_review_rounds=1, plan_approved_first_try=True)
        steps = [{"description": "Step 1", "status": "completed", "result": "done"}]
        verdict, _, metrics = await review_execution(_FakeTask(), steps, "initial", nav_fn, revise_fn, "", max_rounds=5, metrics=metrics)
        assert verdict.approved is True
        assert metrics.total_rounds == 3
        assert metrics.plan_review_rounds == 1
    asyncio.get_event_loop().run_until_complete(_run())


def test_navigator_disabled_noop():
    m = DuoMetrics()
    assert m.total_rounds == 0
    v = NavigatorVerdict(approved=True, needs_user=False, critique="", themes=[])
    assert v.approved is True
