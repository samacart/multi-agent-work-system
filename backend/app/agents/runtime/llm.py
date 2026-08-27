"""Model-backed agent runtime.

Talks to Anthropic or OpenAI directly over HTTP and forces the reply into the
contract's JSON schema - a forced tool call on Anthropic, structured outputs on
OpenAI. If the reply still fails validation it retries once with the validation
error, then gives up and returns a failed run rather than a half-shaped object.

No provider SDK: one small HTTP call per turn, and an injectable transport so
the tests never touch the network.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.agents.contracts import schema_for
from app.agents.runtime.base import AgentContext, AgentProfileLike, AgentRunResult, AgentRuntime
from app.config import get_settings

log = logging.getLogger(__name__)

# Friendly names people actually type, mapped to current API model ids.
MODEL_ALIASES = {
    "claude-opus": "claude-opus-5",
    "claude-sonnet": "claude-sonnet-5",
    "claude-haiku": "claude-haiku-4-5-20251001",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
}

MAX_MEMORIES_IN_PROMPT = 30
MAX_MEMORY_CHARS = 400


def resolve_model(name: str) -> str:
    return MODEL_ALIASES.get(name, name)


def provider_for(model: str) -> str:
    return "anthropic" if resolve_model(model).startswith("claude") else "openai"


def render_context(context: AgentContext) -> str:
    """Everything the agent is allowed to see, as compact text."""
    lines: list[str] = []

    facts = {k: v for k, v in context.extra.items() if isinstance(v, (str, int, float)) and str(v).strip()}
    if facts:
        lines.append("## Project")
        lines.extend(f"- {key}: {value}" for key, value in facts.items())

    lists = {k: v for k, v in context.extra.items() if isinstance(v, list) and v}
    for key, values in lists.items():
        lines.append(f"\n## {key.replace('_', ' ').title()}")
        lines.extend(f"- {str(v)[:MAX_MEMORY_CHARS]}" for v in values[:20])

    if context.memories:
        lines.append("\n## Relevant memory")
        for memory in context.memories[:MAX_MEMORIES_IN_PROMPT]:
            content = str(memory.get("content", ""))[:MAX_MEMORY_CHARS]
            lines.append(
                f"- [{memory.get('type', 'fact')}] (id={memory.get('id')}, "
                f"importance={memory.get('importance')}) {content}"
            )
    else:
        lines.append("\n## Relevant memory\n- none retrieved")

    return "\n".join(lines)


class LlmRuntimeError(Exception):
    pass


class LlmAgentRuntime(AgentRuntime):
    name = "llm"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
        transport: Any = None,
        max_tokens: int = 4096,
    ) -> None:
        settings = get_settings()
        self.model = resolve_model(model or settings.default_agent_model)
        self.provider = provider or provider_for(self.model)
        self.max_tokens = max_tokens
        self._transport = transport  # httpx transport, injected by tests

        if api_key is not None:
            self._api_key = api_key
        elif self.provider == "anthropic":
            self._api_key = settings.anthropic_api_key or ""
        else:
            self._api_key = settings.openai_api_key or ""

        if not self._api_key:
            needed = "ANTHROPIC_API_KEY" if self.provider == "anthropic" else "OPENAI_API_KEY"
            raise LlmRuntimeError(f"AGENT_RUNTIME=llm with model {self.model!r} requires {needed}")

    async def run(
        self,
        agent_profile: AgentProfileLike,
        input: dict[str, Any],
        context: AgentContext | None = None,
    ) -> AgentRunResult:
        context = context or AgentContext()
        task = input.get("task")
        if task is None:
            return AgentRunResult(status="failed", error="LlmAgentRuntime needs a structured task in input['task']")

        try:
            model = schema_for(task)
        except ValueError as exc:
            return AgentRunResult(status="failed", error=str(exc))

        schema = model.model_json_schema()
        system = (
            f"{agent_profile.system_prompt}\n\n"
            f"You are producing the '{task}' output for this project. Reply only through the provided "
            f"structure. Ground every claim in the supplied memory where possible, and say plainly when "
            f"something is unknown rather than inventing it."
        )
        user = f"{input.get('instruction', '')}\n\n{render_context(context)}".strip()

        last_error: str | None = None
        for attempt in (1, 2):
            prompt = user if last_error is None else (
                f"{user}\n\n## Your previous reply did not match the required structure\n{last_error}\n"
                f"Reply again, matching the structure exactly."
            )
            try:
                raw = await self._call(system, prompt, task, schema)
            except LlmRuntimeError as exc:
                return AgentRunResult(status="failed", error=str(exc))

            try:
                validated = model.model_validate(raw)
            except ValidationError as exc:
                last_error = str(exc)[:2000]
                log.warning("llm runtime attempt %d failed validation for %s", attempt, task)
                continue

            return AgentRunResult(status="succeeded", output=validated.model_dump(mode="json"))

        return AgentRunResult(
            status="failed", error=f"Model output did not match the {task} contract after 2 attempts: {last_error}"
        )

    async def _call(self, system: str, prompt: str, task: str, schema: dict) -> dict:
        import httpx

        if self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            tool_name = f"emit_{task}"
            payload = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [{"name": tool_name, "description": f"Return the {task}.", "input_schema": schema}],
                "tool_choice": {"type": "tool", "name": tool_name},
            }
        else:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self._api_key}", "content-type": "application/json"}
            payload = {
                "model": self.model,
                "max_completion_tokens": self.max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": task, "schema": schema, "strict": False},
                },
            }

        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            # Never surface the body: provider errors can echo request content.
            raise LlmRuntimeError(
                f"{self.provider} returned {response.status_code} for model {self.model}"
            )

        return self._extract(response.json())

    def _extract(self, body: dict) -> dict:
        if self.provider == "anthropic":
            for block in body.get("content", []):
                if block.get("type") == "tool_use":
                    return block.get("input") or {}
            raise LlmRuntimeError("Anthropic reply contained no tool_use block")

        choices = body.get("choices") or []
        if not choices:
            raise LlmRuntimeError("OpenAI reply contained no choices")
        content = (choices[0].get("message") or {}).get("content") or ""
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LlmRuntimeError(f"OpenAI reply was not valid JSON: {exc}") from exc
