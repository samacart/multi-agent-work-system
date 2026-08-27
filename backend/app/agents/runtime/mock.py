"""Deterministic runtime used by tests and by Phase 1 wiring.

Makes no network calls. Output is a stable function of the inputs so tests can
assert on it.
"""

from __future__ import annotations

from typing import Any

from app.agents.runtime.base import AgentContext, AgentProfileLike, AgentRunResult, AgentRuntime


class MockAgentRuntime(AgentRuntime):
    name = "mock"

    async def run(
        self,
        agent_profile: AgentProfileLike,
        input: dict[str, Any],
        context: AgentContext | None = None,
    ) -> AgentRunResult:
        context = context or AgentContext()
        return AgentRunResult(
            status="succeeded",
            output={
                "runtime": self.name,
                "agent": agent_profile.name,
                "role": agent_profile.role,
                "summary": f"[mock] {agent_profile.name} handled: {input.get('instruction', 'no instruction')}",
                "input_echo": input,
                "memories_considered": len(context.memories),
                "next_action": "none (mock runtime)",
            },
        )
