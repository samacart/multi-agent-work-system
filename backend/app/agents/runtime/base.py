"""Agent runtime adapter interface.

Nothing above this boundary knows which model provider (or Claude Code, or
LangGraph) actually executes an agent. Phase 6 adds real implementations; the
mock keeps development and tests deterministic and offline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentContext:
    """Everything an agent is allowed to see for one run."""

    project_id: str | None = None
    task_id: str | None = None
    memories: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRunResult:
    status: str  # succeeded | failed
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    approval_requests: list[dict[str, Any]] = field(default_factory=list)


class AgentProfileLike(Protocol):
    name: str
    role: str
    system_prompt: str


class AgentRuntime(ABC):
    """`run(agent_profile, input, context) -> AgentRunResult`."""

    name: str = "base"

    @abstractmethod
    async def run(
        self,
        agent_profile: AgentProfileLike,
        input: dict[str, Any],
        context: AgentContext | None = None,
    ) -> AgentRunResult: ...
