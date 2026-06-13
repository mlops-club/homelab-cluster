"""pydantic-ai Agent + Kitaru observability wrap.

Kitaru is used here ONLY for run/checkpoint tracing visible in its web UI.
HITL pause/resume is handled by `service.py` with a per-chat `asyncio.Event`
— we do NOT call `kitaru.wait()` because that primitive parks a worker
thread polling the Kitaru server every 5s, which means a process can only
handle ~min(32, cpu_count+4) concurrent paused chats before the asyncio
default executor saturates.

The `clarify` tool raises `ClarifyRequested(question, options)` which the
service catches, emits as a `wait` SSE frame, parks an `asyncio.Event`
keyed by chat_id, and re-invokes the agent with the user's answer
prepended to the prompt history on the next chat turn.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from kitaru.adapters.pydantic_ai import KitaruAgent
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class ClarifyRequested(Exception):
    """Raised by `clarify` when the agent decides the prompt is ambiguous."""

    def __init__(self, question: str, options: list[str] | None = None) -> None:
        self.question = question
        self.options = list(options) if options else []
        super().__init__(question)


@dataclass(frozen=True)
class AgentConfig:
    ollama_base_url: str
    model_name: str
    loseit_bin: str
    hours_from_gmt: int


def _user_today(hours_from_gmt: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours_from_gmt)).date().isoformat()


def _system_prompt(today: str) -> str:
    return f"""You log meals to Lose It! by driving the `loseit` CLI via tools.

Today (user's local date) is {today}. Pass `on_date="{today}"` to `log_food` and `diary`.

For EACH food the user mentions:
  1. `search` with the BARE food noun ONLY (no user modifiers like "homemade").
  2. `describe_food` on at least 3 candidate food_ids from search.
  3. Pick a candidate that supports the user's stated unit (grams → entry's
     `primary_serving.unit == "grams"` OR `cross_class_conversion.per_serving_g != null`).
     If none of those 3 work, re-search with different keywords. Up to 3 rounds.
     Sanity-check calories: lentils ~115/100g, asparagus ~20/100g, potatoes ~70/100g,
     guacamole ~150/100g.
  4. `log_food` with the chosen food_id, the user's amount and unit EXACTLY as given,
     meal=snacks unless stated, on_date.
  5. After ALL foods, `diary(on_date)` to confirm.

NEVER convert grams to tablespoons or vice versa. NEVER log spoon-counts > 30.
If a request is genuinely ambiguous ("some berries", "a couple cookies"), call
`clarify(question, options=[...])` BEFORE logging."""


def _run_loseit(cfg: AgentConfig, args: list[str], *, json_output: bool = True) -> str:
    cmd = [cfg.loseit_bin]
    if json_output:
        cmd += ["-o", "json"]
    cmd += args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        err = {"error": "loseit_cli_failed", "exit_code": proc.returncode, "stderr": stderr[:2000]}
        if "doesn't have a tablespoon" in stderr or "unit_not_supported" in stderr:
            err["guidance"] = (
                "This food entry does not support the user's requested unit. "
                "Re-search with different keywords and pick a different food_id "
                "whose primary_serving.unit matches or has cross_class_conversion."
            )
        return json.dumps(err)
    return proc.stdout.strip()


def build_agent(cfg: AgentConfig) -> tuple[KitaruAgent, Agent]:
    """Return (kitaru-wrapped agent, the inner pydantic-ai Agent).

    The inner Agent is exposed so the service can read its message-history
    after a run for resume scenarios.
    """
    model = OpenAIChatModel(
        cfg.model_name,
        provider=OpenAIProvider(base_url=cfg.ollama_base_url, api_key="ollama"),
    )
    inner = Agent(
        model,
        name="loseit-agent",
        system_prompt=_system_prompt(_user_today(cfg.hours_from_gmt)),
        retries=2,
    )
    _register_tools(inner, cfg)
    # Kitaru wrap — observability only. No `allow_sync_tool_body_waits`, no
    # `tool_checkpoint_config_by_name`, no `kitaru.wait()` from inside tools.
    wrapped = KitaruAgent(inner, name="loseit-agent", checkpoint_strategy="calls")
    return wrapped, inner


def _register_tools(agent: Agent, cfg: AgentConfig) -> None:
    @agent.tool_plain
    def clarify(question: str, options: list[str] | None = None) -> str:
        """Pause the run and ask the user to disambiguate.

        Use ONLY when the request names a food generically and the choice
        materially changes calories (e.g. "berries" vs "blueberries").
        """
        raise ClarifyRequested(question, options)

    @agent.tool_plain
    def search(query: str) -> str:
        """Search the Lose It! food database for candidates matching `query`."""
        return _run_loseit(cfg, ["search", query])

    @agent.tool_plain
    def describe_food(food_ids: list[str]) -> str:
        """Inspect one or more foods by hex `food_id`s.

        Returns per-serving math: `primary_serving.unit`,
        `cross_class_conversion.per_serving_g`, and `nutrients_per_serving`.
        Use this to filter for entries that support the user's unit before logging.
        """
        return _run_loseit(cfg, ["describe-food", *food_ids])

    @agent.tool_plain
    def log_food(
        food_id: str,
        meal: Literal["breakfast", "lunch", "dinner", "snacks"],
        serving_amount: float | None = None,
        serving_unit: str | None = None,
        servings: float = 1.0,
        on_date: str | None = None,
    ) -> str:
        """Log a food to the diary. WRITES the entry (no dry_run param)."""
        if serving_unit in {"tsp", "tbsp", "fl_oz"} and serving_amount and serving_amount > 30:
            return json.dumps({
                "error": "agent_guardrail_unit_conversion",
                "guidance": (
                    f"REFUSING: {serving_amount} {serving_unit} is absurdly high. "
                    "You converted grams to spoons; don't. Re-search and pick a "
                    "food_id whose cross_class_conversion.per_serving_g is non-null."
                ),
            })
        args = ["log", "--food-id", food_id, "--meal", meal]
        if serving_amount is not None:
            args += ["--serving-amount", str(serving_amount)]
        if serving_unit:
            args += ["--serving-unit", serving_unit]
        if serving_amount is None and serving_unit is None:
            args += ["--servings", str(servings)]
        if on_date:
            args += ["--date", on_date]
        return _run_loseit(cfg, args, json_output=False)

    @agent.tool_plain
    def diary(on_date: str | None = None) -> str:
        """Read the user's diary for a given date (default: today)."""
        args = ["diary"]
        if on_date:
            args += ["--date", on_date]
        return _run_loseit(cfg, args)

    @agent.tool_plain
    def whoami() -> str:
        """Print resolved Lose It! client configuration."""
        return _run_loseit(cfg, ["whoami"])
