"""Runtime adapters: swappable by config, offline in tests."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents.runtime import available_runtimes, get_runtime
from app.agents.runtime.base import AgentContext, AgentRuntime
from app.agents.runtime.llm import (
    LlmAgentRuntime,
    LlmRuntimeError,
    provider_for,
    render_context,
    resolve_model,
)


class Profile:
    name = "Lead PM"
    role = "lead_pm"
    system_prompt = "You are the Lead PM agent."


BRIEF = {
    "summary": "Ship self-serve onboarding.",
    "goals": ["Let an org sign up unaided"],
    "non_goals": [],
    "assumptions": ["Invites expire after 14 days"],
    "unknowns": [],
    "risks": [{"description": "Expired invites fail silently", "severity": "high", "mitigation": None}],
    "success_criteria": ["An org can sign up without support"],
}

CONTEXT = AgentContext(
    project_id="p1",
    memories=[{"id": "m1", "type": "decision", "content": "Invite links expire after 14 days.", "importance": 0.9}],
    extra={"project_name": "self-serve onboarding", "goal": "let an org sign up unaided"},
)


# --- registry ---


def test_every_runtime_is_registered_and_swappable():
    assert set(available_runtimes()) == {"mock", "llm", "langgraph", "claude_code"}
    assert isinstance(get_runtime("mock"), AgentRuntime)


def test_unknown_runtime_names_what_is_available():
    with pytest.raises(ValueError, match="Available: claude_code, langgraph, llm, mock"):
        get_runtime("nope")


def test_runtimes_are_constructed_lazily():
    """Listing must not construct runtimes - most raise without a provider."""
    from app.config import get_settings

    settings = get_settings()
    key = settings.anthropic_api_key
    settings.anthropic_api_key = None
    try:
        assert "llm" in available_runtimes()
        with pytest.raises(LlmRuntimeError, match="ANTHROPIC_API_KEY"):
            get_runtime("llm")
    finally:
        settings.anthropic_api_key = key


# --- model naming ---


def test_friendly_model_names_resolve_and_pick_a_provider():
    assert resolve_model("claude-sonnet") == "claude-sonnet-5"
    assert resolve_model("claude-opus-5") == "claude-opus-5"
    assert provider_for("claude-sonnet") == "anthropic"
    assert provider_for("gpt-4o") == "openai"


def test_context_rendering_includes_memory_and_scope():
    rendered = render_context(CONTEXT)
    assert "self-serve onboarding" in rendered
    assert "Invite links expire after 14 days." in rendered
    assert "id=m1" in rendered


def test_context_rendering_says_when_there_is_no_memory():
    assert "none retrieved" in render_context(AgentContext())


# --- llm runtime, against a stubbed transport ---


def _anthropic_transport(payloads: list[dict], captured: list | None = None):
    replies = list(payloads)

    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(json.loads(request.content))
        body = replies.pop(0)
        if isinstance(body, int):
            return httpx.Response(body, json={"error": "nope"})
        return httpx.Response(200, json={"content": [{"type": "tool_use", "input": body}]})

    return httpx.MockTransport(handler)


def _llm(transport, model="claude-sonnet-5") -> LlmAgentRuntime:
    return LlmAgentRuntime(model=model, api_key="test-key", transport=transport)


async def test_llm_runtime_returns_validated_structured_output():
    captured: list = []
    runtime = _llm(_anthropic_transport([BRIEF], captured))

    result = await runtime.run(Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT)

    assert result.status == "succeeded"
    assert result.output["goals"] == ["Let an org sign up unaided"]

    sent = captured[0]
    assert sent["tool_choice"] == {"type": "tool", "name": "emit_project_brief"}
    assert sent["tools"][0]["input_schema"]["properties"]["summary"]
    assert "Invite links expire after 14 days." in sent["messages"][0]["content"]


async def test_llm_runtime_repairs_a_malformed_reply_once():
    captured: list = []
    runtime = _llm(_anthropic_transport([{"wrong": "shape"}, BRIEF], captured))

    result = await runtime.run(Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT)

    assert result.status == "succeeded"
    assert len(captured) == 2
    assert "did not match the required structure" in captured[1]["messages"][0]["content"]


async def test_llm_runtime_gives_up_rather_than_returning_a_half_shape():
    runtime = _llm(_anthropic_transport([{"wrong": "shape"}, {"still": "wrong"}]))

    result = await runtime.run(Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT)

    assert result.status == "failed"
    assert "after 2 attempts" in result.error


async def test_llm_runtime_does_not_leak_the_provider_error_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key sk-ant-secret"}})

    result = await _llm(httpx.MockTransport(handler)).run(
        Profile(), {"task": "project_brief", "instruction": "x"}, CONTEXT
    )

    assert result.status == "failed"
    assert "401" in result.error
    assert "sk-ant-secret" not in result.error


async def test_llm_runtime_speaks_openai_when_the_model_is_openai():
    captured: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        assert "openai.com" in str(request.url)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(BRIEF)}}]}
        )

    runtime = LlmAgentRuntime(model="gpt-4o", api_key="test-key", transport=httpx.MockTransport(handler))
    result = await runtime.run(Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT)

    assert result.status == "succeeded"
    assert captured[0]["response_format"]["json_schema"]["name"] == "project_brief"


async def test_llm_runtime_rejects_an_unknown_task():
    result = await _llm(_anthropic_transport([BRIEF])).run(Profile(), {"task": "nonsense"}, CONTEXT)
    assert result.status == "failed"
    assert "Unknown agent task" in result.error


async def test_llm_runtime_needs_a_structured_task():
    result = await _llm(_anthropic_transport([BRIEF])).run(Profile(), {"instruction": "just chat"}, CONTEXT)
    assert result.status == "failed"
    assert "structured task" in result.error


# --- claude code host adapter ---


def _claude_code(runner):  # noqa: ANN001, ANN202
    from app.agents.runtime.claude_code import ClaudeCodeRuntime

    return ClaudeCodeRuntime(runner=runner)


async def test_claude_code_parses_a_bare_json_reply():
    runtime = _claude_code(lambda prompt: _echo(json.dumps(BRIEF)))
    result = await runtime.run(Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT)
    assert result.status == "succeeded"
    assert result.output["summary"] == BRIEF["summary"]


async def test_claude_code_unwraps_the_cli_result_envelope():
    """`claude -p --output-format json` wraps the answer in an envelope."""
    envelope = json.dumps({"type": "result", "result": f"Here you go:\n```json\n{json.dumps(BRIEF)}\n```"})
    result = await _claude_code(lambda prompt: _echo(envelope)).run(
        Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT
    )
    assert result.status == "succeeded"
    assert result.output["goals"] == BRIEF["goals"]


async def test_claude_code_digs_json_out_of_surrounding_prose():
    reply = f"I looked at the repo. {json.dumps(BRIEF)} Let me know if that works."
    result = await _claude_code(lambda prompt: _echo(reply)).run(
        Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT
    )
    assert result.status == "succeeded"


async def test_claude_code_reports_unusable_output():
    result = await _claude_code(lambda prompt: _echo("I could not do that.")).run(
        Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT
    )
    assert result.status == "failed"
    assert "no JSON object" in result.error


async def test_claude_code_rejects_output_that_breaks_the_contract():
    result = await _claude_code(lambda prompt: _echo(json.dumps({"wrong": "shape"}))).run(
        Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT
    )
    assert result.status == "failed"
    assert "did not match the project_brief contract" in result.error


async def test_claude_code_prompt_carries_the_schema_and_the_memory():
    seen: list[str] = []

    async def runner(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps(BRIEF)

    await _claude_code(runner).run(Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT)

    assert "JSON Schema" in seen[0]
    assert "Invite links expire after 14 days." in seen[0]
    assert "You are the Lead PM agent." in seen[0]


def test_claude_code_says_where_to_run_it_when_the_binary_is_missing():
    from app.agents.runtime.claude_code import ClaudeCodeRuntime, ClaudeCodeUnavailable

    with pytest.raises(ClaudeCodeUnavailable, match="not expected to be available inside the API container"):
        ClaudeCodeRuntime(binary="definitely-not-a-real-binary-9182")


async def _echo(text: str) -> str:
    return text


# --- langgraph runtime ---


class ScriptedRuntime(AgentRuntime):
    """Returns the next scripted reply on each call."""

    name = "scripted"

    def __init__(self, replies: list) -> None:
        from app.agents.runtime.base import AgentRunResult

        self.replies = list(replies)
        self.calls: list[dict] = []
        self._result = AgentRunResult

    async def run(self, agent_profile, input, context=None):  # noqa: ANN001, ANN201
        self.calls.append(input)
        reply = self.replies.pop(0)
        if isinstance(reply, str):
            return self._result(status="failed", error=reply)
        return self._result(status="succeeded", output=reply)


async def test_langgraph_runtime_returns_validated_output():
    from app.agents.runtime.graph import LangGraphAgentRuntime

    generator = ScriptedRuntime([BRIEF])
    result = await LangGraphAgentRuntime(generator=generator).run(
        Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT
    )

    assert result.status == "succeeded"
    assert result.output["summary"] == BRIEF["summary"]
    assert len(generator.calls) == 1


async def test_langgraph_runtime_repairs_through_a_declared_edge():
    from app.agents.runtime.graph import LangGraphAgentRuntime

    generator = ScriptedRuntime([{"wrong": "shape"}, BRIEF])
    result = await LangGraphAgentRuntime(generator=generator).run(
        Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT
    )

    assert result.status == "succeeded"
    assert len(generator.calls) == 2
    # The repair carries the validation error forward as state.
    assert "did not match the required structure" in generator.calls[1]["instruction"]


async def test_langgraph_runtime_bounds_its_attempts():
    from app.agents.runtime.graph import LangGraphAgentRuntime

    generator = ScriptedRuntime([{"wrong": "shape"}] * 5)
    result = await LangGraphAgentRuntime(generator=generator, max_attempts=3).run(
        Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT
    )

    assert result.status == "failed"
    assert "gave up after 3 attempt(s)" in result.error
    assert len(generator.calls) == 3


async def test_langgraph_runtime_surfaces_a_generator_failure():
    from app.agents.runtime.graph import LangGraphAgentRuntime

    generator = ScriptedRuntime(["provider unreachable"] * 3)
    result = await LangGraphAgentRuntime(generator=generator, max_attempts=2).run(
        Profile(), {"task": "project_brief", "instruction": "plan it"}, CONTEXT
    )

    assert result.status == "failed"
    assert "provider unreachable" in result.error


# --- the point of all of it: orchestration does not know which runtime it got ---


async def test_planning_runs_end_to_end_on_a_non_mock_runtime(session):
    """The acceptance criterion for the adapter: swap the runtime by config and
    the same planning code path works, recording which runtime produced each run."""
    from sqlalchemy import select

    from app.db.models import AgentRun, Project, Task
    from app.db.seed import seed_agent_profiles
    from app.projects.planning import plan_project

    await seed_agent_profiles(session)
    project = Project(name="self-serve onboarding", goal="let an org sign up unaided")
    session.add(project)
    await session.commit()

    # One canned reply per contract the planner asks for.
    replies = {
        "domain_context": {"summary": "Nothing recorded yet.", "cited_memory_ids": []},
        "project_brief": BRIEF,
        "architecture_plan": {"approach": "Follow existing patterns.", "impacted_areas": ["invites"]},
        "task_breakdown": {
            "tasks": [
                {
                    "title": "Design invite expiry",
                    "description": "Define storage and expiry.",
                    "agent_role": "architect",
                    "acceptance_criteria": ["Expiry behaviour is defined"],
                    "depends_on": [],
                }
            ]
        },
        "questions": {"questions": [{"question": "How long should invites last?", "why_it_matters": "scope"}]},
        "approvals": {"approvals": [{"action_type": "change_database_schema", "action_summary": "new table", "risk_level": "high"}]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        task = body["tools"][0]["input_schema"]["title"]
        by_title = {
            "DomainContext": "domain_context",
            "ProjectBrief": "project_brief",
            "ArchitecturePlan": "architecture_plan",
            "TaskBreakdown": "task_breakdown",
            "QuestionSet": "questions",
            "ApprovalSet": "approvals",
        }
        return httpx.Response(
            200, json={"content": [{"type": "tool_use", "input": replies[by_title[task]]}]}
        )

    runtime = _llm(httpx.MockTransport(handler))
    import app.orchestration.runs as runs_module

    original = runs_module.get_runtime
    runs_module.get_runtime = lambda: runtime
    try:
        result = await plan_project(session, project.id)
    finally:
        runs_module.get_runtime = original

    assert result.status == "ready"
    assert result.tasks_created == 1

    runs = (await session.scalars(select(AgentRun))).all()
    assert len(runs) == 6
    assert {r.input["runtime"] for r in runs} == {"llm"}

    task = (await session.scalars(select(Task))).one()
    assert task.title == "Design invite expiry"
    assert task.agent_role == "architect"


# --- claude code is destructive by default and must be constrained ---


def test_claude_code_is_read_only_by_default():
    """Headless `claude -p` edits files with no permission prompt - verified
    against the real CLI. There is no interactive gate to fall back on, so the
    constraint has to be passed explicitly on every invocation."""
    from app.config import get_settings

    settings = get_settings()
    flags = settings.claude_code_tool_flags

    assert "--disallowedTools" in flags
    blocked = flags[flags.index("--disallowedTools") + 1]
    for tool in ("Edit", "Write", "Bash"):
        assert tool in blocked
    assert settings.claude_code_can_write is False


def test_the_runtime_passes_its_tool_flags_to_the_cli():
    from app.agents.runtime.claude_code import ClaudeCodeRuntime

    runtime = _claude_code(lambda prompt: _echo(json.dumps(BRIEF)))
    assert "--disallowedTools" in runtime.tool_flags

    explicit = ClaudeCodeRuntime(runner=lambda p: _echo("{}"), tool_flags=["--allowedTools", "Read"])
    assert explicit.tool_flags == ["--allowedTools", "Read"]


def test_enabling_writes_is_visible_in_config(monkeypatch):
    """Turning writes on should be legible, not buried in a tool string."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "claude_code_disallowed_tools", "NotebookEdit")
    assert settings.claude_code_can_write is True
