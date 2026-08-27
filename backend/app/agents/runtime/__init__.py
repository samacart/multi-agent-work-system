"""Agent runtime adapters, selected by the AGENT_RUNTIME setting.

Every runtime satisfies the same contract - `run(profile, input, context) ->
AgentRunResult` - so orchestration never learns which one is configured.
Runtimes are constructed lazily, because most of them raise on construction
when their provider is not configured.
"""

from __future__ import annotations

from collections.abc import Callable

from app.agents.runtime.base import AgentContext, AgentRunResult, AgentRuntime
from app.agents.runtime.mock import MockAgentRuntime


def _llm() -> AgentRuntime:
    from app.agents.runtime.llm import LlmAgentRuntime

    return LlmAgentRuntime()


def _langgraph() -> AgentRuntime:
    from app.agents.runtime.graph import LangGraphAgentRuntime

    return LangGraphAgentRuntime()


def _claude_code() -> AgentRuntime:
    from app.agents.runtime.claude_code import ClaudeCodeRuntime

    return ClaudeCodeRuntime()


_RUNTIMES: dict[str, Callable[[], AgentRuntime]] = {
    "mock": MockAgentRuntime,
    "llm": _llm,
    "langgraph": _langgraph,
    "claude_code": _claude_code,
}


def available_runtimes() -> list[str]:
    return sorted(_RUNTIMES)


def get_runtime(name: str | None = None) -> AgentRuntime:
    from app.config import get_settings

    key = (name or get_settings().agent_runtime).lower()
    try:
        factory = _RUNTIMES[key]
    except KeyError:
        raise ValueError(
            f"Unknown agent runtime {key!r}. Available: {', '.join(available_runtimes())}"
        ) from None
    return factory()


__all__ = [
    "AgentContext",
    "AgentRunResult",
    "AgentRuntime",
    "MockAgentRuntime",
    "available_runtimes",
    "get_runtime",
]
