"""Kitaru flow wrapping a pydantic-ai agent that drives the loseit CLI.

Deployment (one-time, from a machine logged into the Kitaru server):

    kitaru deploy \\
      apps/loseit-kitaru-workflow/src/loseit_kitaru_workflow/flow.py:loseit_agent_flow \\
      --name loseit_agent_flow \\
      --image '{"requirements": ["loseit-kitaru-workflow"]}'

Invocation (from anything — e.g. loseit-openwebui-agent):

    from kitaru.client import KitaruClient
    handle = KitaruClient().deployments.invoke(
        flow="loseit_agent_flow",
        inputs={"prompt": "log 100g guacamole", "chat_id": "abc123"},
    )

HITL via `@hitl_tool` — when the agent calls `clarify(question=...)`, the
deployed flow pauses at a wait condition that the FastAPI tier resolves
with `KitaruClient().executions.input(exec_id, wait_name, value)`.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Literal

import kitaru
from kitaru.adapters.pydantic_ai import KitaruAgent, hitl_tool
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", "http://ollama.ollama.svc.cluster.local:11434/v1"
)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
LOSEIT_BIN = os.environ.get("LOSEIT_BIN", "loseit")


def _user_today() -> str:
    offset = int(os.environ.get("LOSEIT_HOURS_FROM_GMT", "-6"))
    return (datetime.now(timezone.utc) + timedelta(hours=offset)).date().isoformat()


SYSTEM_PROMPT = f"""You log meals to Lose It! by driving the `loseit` CLI via tools.

Today is {_user_today()}. Pass on_date="{_user_today()}" to log_food and diary.

For each food:
  1. search with the bare food noun.
  2. describe_food on 3 candidates.
  3. Pick one supporting the user's unit (grams → primary_serving.unit=="grams"
     or non-null cross_class_conversion.per_serving_g).
  4. log_food with the user's amount and unit EXACTLY as given.
  5. diary(on_date) to confirm.

Never convert grams to spoons. Never log spoon-counts > 30.
If the request is genuinely ambiguous, call clarify(question=...)."""


def _run_loseit(args: list[str], json_output: bool = True) -> str:
    cmd = [LOSEIT_BIN]
    if json_output:
        cmd += ["-o", "json"]
    cmd += args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        return json.dumps({
            "error": "loseit_cli_failed",
            "exit_code": proc.returncode,
            "stderr": proc.stderr.strip()[:2000],
        })
    return proc.stdout.strip()


_model = OpenAIChatModel(
    OLLAMA_MODEL,
    provider=OpenAIProvider(base_url=OLLAMA_BASE_URL, api_key="ollama"),
)

_inner_agent: Agent[None, str] = Agent(
    _model,
    name="loseit-agent",
    system_prompt=SYSTEM_PROMPT,
    retries=2,
)


@_inner_agent.tool_plain
def search(query: str) -> str:
    """Search the Lose It! food database."""
    return _run_loseit(["search", query])


@_inner_agent.tool_plain
def describe_food(food_ids: list[str]) -> str:
    """Inspect 1+ foods by hex food_id."""
    return _run_loseit(["describe-food", *food_ids])


@_inner_agent.tool_plain
def log_food(
    food_id: str,
    meal: Literal["breakfast", "lunch", "dinner", "snacks"],
    serving_amount: float | None = None,
    serving_unit: str | None = None,
    servings: float = 1.0,
    on_date: str | None = None,
) -> str:
    """Log a food to the diary."""
    if serving_unit in {"tsp", "tbsp", "fl_oz"} and serving_amount and serving_amount > 30:
        return json.dumps({
            "error": "agent_guardrail_unit_conversion",
            "guidance": f"REFUSING: {serving_amount} {serving_unit} is absurdly high.",
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
    return _run_loseit(args, json_output=False)


@_inner_agent.tool_plain
def diary(on_date: str | None = None) -> str:
    """Read the user's diary for a given date."""
    args = ["diary"]
    if on_date:
        args += ["--date", on_date]
    return _run_loseit(args)


@_inner_agent.tool_plain
def whoami() -> str:
    """Print resolved Lose It! client configuration."""
    return _run_loseit(["whoami"])


@_inner_agent.tool_plain
@hitl_tool(question_arg="question", schema=str)
def clarify(question: str, options: list[str] | None = None) -> str:
    """Pause the flow and ask the user to disambiguate.

    Use ONLY when the request names a food generically and the choice
    materially changes calories. The flow pauses at a Kitaru wait
    condition; the FastAPI tier resolves it via
    `client.executions.input(exec_id, wait_name, user_answer)`.
    """


_durable_agent = KitaruAgent(
    _inner_agent,
    name="loseit-agent",
    checkpoint_strategy="calls",
    persist_message_history=True,
)


@kitaru.flow
def loseit_agent_flow(prompt: str, chat_id: str | None = None) -> str:
    """Run the loseit pydantic-ai agent as a durable Kitaru flow.

    Inputs:
      prompt: natural-language user request
      chat_id: optional, used only as a metadata tag for run-grouping in
        Kitaru's UI; the flow itself is stateless across invocations
        (each invocation is a fresh execution snapshot per Kitaru's
        deployment model).
    """
    if chat_id:
        kitaru.log_metadata({"chat_id": chat_id})
    return _durable_agent.run_sync(prompt).output
