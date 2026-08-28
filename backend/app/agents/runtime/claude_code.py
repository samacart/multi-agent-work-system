"""Claude Code host adapter.

Claude Code is a CLI with filesystem and shell access; it is deliberately not
assumed to run inside the API container. This adapter shells out to it, so the
usual deployment is to run the backend on the host (or point CLAUDE_CODE_BINARY
at a wrapper that reaches one).

It is the runtime to use when an agent needs to actually read a repository, edit
files, and run tests - the things no other runtime here can do.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from typing import Any

from pydantic import ValidationError

from app.agents.contracts import schema_for
from app.agents.runtime.base import AgentContext, AgentProfileLike, AgentRunResult, AgentRuntime
from app.agents.runtime.llm import render_context
from app.config import get_settings

log = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)

# Idle Claude Code sessions available for reuse, keyed by pool name. A session
# is a linear conversation, so two concurrent passes must never share one -
# hence a pool of sessions to borrow from rather than one session per project.
_SESSION_POOL: dict[str, list[str]] = {}
_POOL_LOCK = asyncio.Lock()


async def _borrow_session(key: str) -> str | None:
    async with _POOL_LOCK:
        pool = _SESSION_POOL.get(key) or []
        return pool.pop() if pool else None


async def _return_session(key: str, session_id: str) -> None:
    async with _POOL_LOCK:
        _SESSION_POOL.setdefault(key, []).append(session_id)


def clear_session_pool() -> None:
    _SESSION_POOL.clear()


class ClaudeCodeUnavailable(Exception):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a CLI reply that may wrap it in prose."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Claude Code returned no output")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = _FENCE_RE.search(text)
    if fenced:
        return json.loads(fenced.group(1))

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("Claude Code output contained no JSON object")


class ClaudeCodeRuntime(AgentRuntime):
    name = "claude_code"

    def __init__(
        self,
        binary: str | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
        runner=None,  # noqa: ANN001 - injected in tests
        tool_flags: list[str] | None = None,
        reuse_sessions: bool | None = None,
    ) -> None:
        settings = get_settings()
        self.binary = binary or settings.claude_code_binary
        self.cwd = cwd or settings.claude_code_cwd or None
        self.timeout = timeout or settings.claude_code_timeout_seconds
        self._runner = runner
        # Headless `claude -p` edits files without prompting, so the constraint
        # has to be passed explicitly - there is no interactive gate to fall
        # back on.
        self.tool_flags = settings.claude_code_tool_flags if tool_flags is None else tool_flags
        self.reuse_sessions = (
            settings.claude_code_reuse_sessions if reuse_sessions is None else reuse_sessions
        )

        if self._runner is None and shutil.which(self.binary) is None:
            raise ClaudeCodeUnavailable(
                f"Claude Code binary {self.binary!r} was not found on PATH. It is not expected to be "
                "available inside the API container - run the backend on the host, or point "
                "CLAUDE_CODE_BINARY at a wrapper that reaches one."
            )

    async def run(
        self,
        agent_profile: AgentProfileLike,
        input: dict[str, Any],
        context: AgentContext | None = None,
    ) -> AgentRunResult:
        context = context or AgentContext()
        task = input.get("task")
        if task is None:
            return AgentRunResult(status="failed", error="ClaudeCodeRuntime needs a structured task in input['task']")

        try:
            model = schema_for(task)
        except ValueError as exc:
            return AgentRunResult(status="failed", error=str(exc))

        prompt = self._build_prompt(agent_profile, task, model.model_json_schema(), input, context)

        # Reusing a session skips re-exploring the repository from cold, which
        # dominates the cost of a pass. Borrowed, not shared: a session is one
        # linear conversation.
        pool_key = str(input.get("session_pool") or "") if self.reuse_sessions else ""
        resume_id = await _borrow_session(pool_key) if pool_key else None

        try:
            stdout = await self._invoke(prompt, resume_id)
        except (ClaudeCodeUnavailable, asyncio.TimeoutError) as exc:
            return AgentRunResult(status="failed", error=str(exc) or "Claude Code timed out")

        try:
            payload = _extract_json(stdout)
        except (ValueError, json.JSONDecodeError) as exc:
            return AgentRunResult(status="failed", error=f"Could not read Claude Code output as JSON: {exc}")

        if pool_key and isinstance(payload.get("session_id"), str):
            await _return_session(pool_key, payload["session_id"])

        # `claude -p --output-format json` wraps the answer in an envelope.
        if "result" in payload and not set(model.model_fields) & set(payload):
            try:
                payload = _extract_json(str(payload["result"]))
            except (ValueError, json.JSONDecodeError) as exc:
                return AgentRunResult(status="failed", error=f"Claude Code result field held no JSON: {exc}")

        try:
            validated = model.model_validate(payload)
        except ValidationError as exc:
            return AgentRunResult(status="failed", error=f"Output did not match the {task} contract: {exc}")

        return AgentRunResult(status="succeeded", output=validated.model_dump(mode="json"))

    def _build_prompt(
        self,
        profile: AgentProfileLike,
        task: str,
        schema: dict,
        input: dict[str, Any],
        context: AgentContext,
    ) -> str:
        return (
            f"{profile.system_prompt}\n\n"
            f"# Task\n{input.get('instruction', '')}\n\n"
            f"{render_context(context)}\n\n"
            f"# Required output\n"
            f"Reply with a single JSON object for '{task}' matching this JSON Schema, and nothing else:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```"
        )

    async def _invoke(self, prompt: str, resume_id: str | None = None) -> str:
        if self._runner is not None:
            return await self._runner(prompt)

        resume_flags = ["--resume", resume_id] if resume_id else []
        process = await asyncio.create_subprocess_exec(
            self.binary,
            "-p",
            prompt,
            "--output-format",
            "json",
            *resume_flags,
            *self.tool_flags,
            cwd=self.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ClaudeCodeUnavailable(f"Claude Code timed out after {self.timeout}s") from None

        if process.returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace").strip()[:500]
            raise ClaudeCodeUnavailable(f"Claude Code exited {process.returncode}: {detail}")

        return (stdout or b"").decode("utf-8", errors="replace")
