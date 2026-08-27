"""LangGraph agent runtime.

Wraps a generating runtime in an explicit state graph:

    prepare -> generate -> validate -> (repair -> generate)* -> done

The value over calling a model directly is that the repair loop is a declared
edge rather than a hidden retry: the number of attempts is bounded and visible,
and each attempt's validation error is carried forward as state. It is also the
seam where later work - tool nodes, subagent fan-out, checkpointed
human-in-the-loop interrupts - attaches without rewriting the callers.

LangGraph is an optional dependency; without it this runtime refuses to start
and says which extra to install.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from pydantic import ValidationError

from app.agents.contracts import schema_for
from app.agents.runtime.base import AgentContext, AgentProfileLike, AgentRunResult, AgentRuntime

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


class LangGraphUnavailable(Exception):
    pass


class GraphState(TypedDict, total=False):
    task: str
    instruction: str
    attempts: int
    raw: dict[str, Any]
    output: dict[str, Any]
    error: str | None


def _require_langgraph():  # noqa: ANN202
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise LangGraphUnavailable(
            "AGENT_RUNTIME=langgraph needs the optional dependency. Install it with "
            "`pip install '.[langgraph]'`."
        ) from exc
    return START, END, StateGraph


class LangGraphAgentRuntime(AgentRuntime):
    name = "langgraph"

    def __init__(self, generator: AgentRuntime | None = None, max_attempts: int = MAX_ATTEMPTS) -> None:
        self._start, self._end, self._state_graph = _require_langgraph()
        self.max_attempts = max_attempts

        if generator is None:
            from app.agents.runtime.llm import LlmAgentRuntime

            generator = LlmAgentRuntime()
        self.generator = generator

    def _build(self, profile: AgentProfileLike, context: AgentContext, model):  # noqa: ANN001, ANN202
        async def prepare(state: GraphState) -> GraphState:
            return {"attempts": 0, "error": None}

        async def generate(state: GraphState) -> GraphState:
            payload: dict[str, Any] = {"task": state["task"], "instruction": state["instruction"]}
            if state.get("error"):
                payload["instruction"] = (
                    f"{state['instruction']}\n\nYour previous reply did not match the required "
                    f"structure:\n{state['error']}\nReply again, matching it exactly."
                )
            result = await self.generator.run(profile, payload, context)
            if result.status != "succeeded":
                return {"attempts": state.get("attempts", 0) + 1, "error": result.error, "raw": {}}
            return {"attempts": state.get("attempts", 0) + 1, "raw": result.output, "error": None}

        async def validate(state: GraphState) -> GraphState:
            if state.get("error") and not state.get("raw"):
                return {}
            try:
                validated = model.model_validate(state.get("raw") or {})
            except ValidationError as exc:
                return {"error": str(exc)[:2000], "output": {}}
            return {"output": validated.model_dump(mode="json"), "error": None}

        def route(state: GraphState) -> str:
            if not state.get("error"):
                return "done"
            if state.get("attempts", 0) >= self.max_attempts:
                return "done"
            return "repair"

        async def repair(state: GraphState) -> GraphState:
            log.info("langgraph runtime repairing attempt %d for %s", state.get("attempts"), state.get("task"))
            return {}

        graph = self._state_graph(GraphState)
        graph.add_node("prepare", prepare)
        graph.add_node("generate", generate)
        graph.add_node("validate", validate)
        graph.add_node("repair", repair)

        graph.add_edge(self._start, "prepare")
        graph.add_edge("prepare", "generate")
        graph.add_edge("generate", "validate")
        graph.add_conditional_edges("validate", route, {"repair": "repair", "done": self._end})
        graph.add_edge("repair", "generate")
        return graph.compile()

    async def run(
        self,
        agent_profile: AgentProfileLike,
        input: dict[str, Any],
        context: AgentContext | None = None,
    ) -> AgentRunResult:
        context = context or AgentContext()
        task = input.get("task")
        if task is None:
            return AgentRunResult(
                status="failed", error="LangGraphAgentRuntime needs a structured task in input['task']"
            )

        try:
            model = schema_for(task)
        except ValueError as exc:
            return AgentRunResult(status="failed", error=str(exc))

        app = self._build(agent_profile, context, model)
        final: GraphState = await app.ainvoke(
            {"task": task, "instruction": str(input.get("instruction", ""))}
        )

        if final.get("error") or not final.get("output"):
            return AgentRunResult(
                status="failed",
                error=(
                    f"Graph gave up after {final.get('attempts')} attempt(s): "
                    f"{final.get('error') or 'no output produced'}"
                ),
            )
        return AgentRunResult(status="succeeded", output=final["output"])
