"""Agent runtime adapter boundary."""

from __future__ import annotations

import pytest

from app.agents.runtime import AgentContext, MockAgentRuntime, get_runtime
from app.agents.runtime.base import AgentRuntime


async def test_mock_runtime_returns_structured_result():
    runtime = MockAgentRuntime()

    class Profile:
        name = "Lead PM"
        role = "lead_pm"
        system_prompt = "..."

    result = await runtime.run(
        Profile(),
        {"instruction": "plan the onboarding project"},
        AgentContext(project_id="p1", memories=[{"content": "invite links expire in 14 days"}]),
    )

    assert result.status == "succeeded"
    assert result.error is None
    assert result.output["role"] == "lead_pm"
    assert result.output["memories_considered"] == 1
    assert "plan the onboarding project" in result.output["summary"]


async def test_mock_runtime_is_deterministic():
    class Profile:
        name = "QA/Test"
        role = "qa"
        system_prompt = "..."

    a = await MockAgentRuntime().run(Profile(), {"instruction": "verify"})
    b = await MockAgentRuntime().run(Profile(), {"instruction": "verify"})
    assert a.output == b.output


def test_runtime_is_selected_by_config():
    runtime = get_runtime("mock")
    assert isinstance(runtime, AgentRuntime)
    assert runtime.name == "mock"


def test_unknown_runtime_fails_loudly():
    with pytest.raises(ValueError, match="Unknown agent runtime"):
        get_runtime("does-not-exist")
