"""Agent runtime adapters, selected by the AGENT_RUNTIME setting."""

from __future__ import annotations

from app.agents.runtime.base import AgentContext, AgentRunResult, AgentRuntime
from app.agents.runtime.mock import MockAgentRuntime

_RUNTIMES: dict[str, type[AgentRuntime]] = {
    "mock": MockAgentRuntime,
}


def get_runtime(name: str | None = None) -> AgentRuntime:
    from app.config import get_settings

    key = (name or get_settings().agent_runtime).lower()
    try:
        return _RUNTIMES[key]()
    except KeyError:
        available = ", ".join(sorted(_RUNTIMES))
        raise ValueError(f"Unknown agent runtime {key!r}. Available: {available}") from None


__all__ = ["AgentContext", "AgentRunResult", "AgentRuntime", "MockAgentRuntime", "get_runtime"]
