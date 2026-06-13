"""Kitaru flow wrapping a pydantic-ai agent that drives the Lose-It SDK.

Architecture: this flow runs on a Kitaru Kubernetes orchestrator pod (one
pod per invocation). The FastAPI gateway (apps/loseit-openwebui-agent/)
calls `KitaruClient().deployments.invoke(flow="loseit_agent_flow", ...)`
and streams `client.executions.events(exec_id)` back to the Open WebUI
Pipe.

Each tool is wrapped with `@kitaru.checkpoint` so the Kitaru UI shows
the full per-tool trace instead of a single `loseit_agent` checkpoint.

Tool returns are TOON-formatted (compact, header+rows for object lists)
because raw JSON for search/diary results was visually noisy in the
chat (per-row keys repeated, a 4-KB result_preview filled the screen).
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

import kitaru
from kitaru.adapters.pydantic_ai import KitaruAgent, hitl_tool
from lose_it import LoseIt
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", "http://ollama.ollama.svc.cluster.local:11434/v1"
)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")


def _user_today() -> str:
    offset = int(os.environ.get("LOSEIT_HOURS_FROM_GMT", "-6"))
    return (datetime.now(timezone.utc) + timedelta(hours=offset)).date().isoformat()


def _system_prompt(today: str) -> str:
    return f"""You log meals to Lose It! via tools backed by the official SDK.

Today (user's local date) is {today}. Pass on_date="{today}" to log_food and diary.

For EACH food the user mentions:
  1. search with the bare food noun ONLY (no user modifiers).
  2. describe_foods on at least 3 candidate food_ids.
  3. Pick a candidate that supports the user's stated unit.
     If none of those 3 work, re-search with different keywords. Up to 3 rounds.
     Sanity-check calories: lentils ~115/100g, asparagus ~20/100g, potatoes ~70/100g,
     guacamole ~150/100g.
  4. log_food with the chosen food_id, the user's amount and unit EXACTLY as given,
     meal=snacks unless stated, on_date.
  5. After ALL foods, diary(on_date) to confirm.

NEVER convert grams to tablespoons or vice versa. NEVER log spoon-counts > 30.
If a request is genuinely ambiguous, call clarify(question, options=[...])."""


# TOON-ish encoder: object lists become header+rows; scalars+dicts fall
# through to compact JSON. Flatten one level of nesting so keys stay short.


def _flatten_one(d: dict, prefix: str = "") -> dict:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten_one(v, prefix=f"{key}."))
        else:
            out[key] = v
    return out


def _to_dict(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _toon(obj: Any) -> str:
    data = _to_dict(obj)
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        rows = [_flatten_one(x) for x in data]
        keys = list({k: None for r in rows for k in r}.keys())
        header = "\t".join(keys)
        lines = [header]
        for r in rows:
            lines.append("\t".join("" if r.get(k) is None else str(r.get(k)) for k in keys))
        return "\n".join(lines)
    return json.dumps(data, separators=(",", ":"), default=str)


_client: LoseIt | None = None


def _hydrate_creds_from_k8s_secret() -> None:
    """Set LOSEIT_* env from in-cluster Kubernetes Secret `loseit-token`.

    Kitaru's KubernetesOrchestrator does not propagate component-level
    `environment` template expansions or `pod_settings.env` entries to
    the workflow step pod, so we hop directly to the K8s API. The
    workflow ServiceAccount (kitaru-workflow-runner) is granted
    secrets/get in the orchestrator namespace via Role
    kitaru-workflow-pod-runner.
    """
    if os.environ.get("LOSEIT_TOKEN"):
        return
    try:
        from kubernetes import client as kclient, config as kconfig
    except ImportError:
        return
    try:
        kconfig.load_incluster_config()
    except Exception:
        return
    ns_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    namespace = open(ns_path).read().strip() if os.path.exists(ns_path) else "loseit-workflow"
    try:
        secret = kclient.CoreV1Api().read_namespaced_secret("loseit-token", namespace)
    except Exception:
        return
    import base64
    for sdk_key, env_key in (
        ("token", "LOSEIT_TOKEN"),
        ("user_name", "LOSEIT_USER_NAME"),
        ("user_id", "LOSEIT_USER_ID"),
        ("hours_from_gmt", "LOSEIT_HOURS_FROM_GMT"),
    ):
        raw = (secret.data or {}).get(sdk_key)
        if raw and not os.environ.get(env_key):
            os.environ[env_key] = base64.b64decode(raw).decode()


def _li() -> LoseIt:
    global _client
    if _client is None:
        _hydrate_creds_from_k8s_secret()
        _client = LoseIt.from_env()
    return _client


_model = OpenAIChatModel(
    OLLAMA_MODEL,
    provider=OpenAIProvider(base_url=OLLAMA_BASE_URL, api_key="ollama"),
)

_inner_agent: Agent[None, str] = Agent(
    _model,
    name="loseit-agent",
    system_prompt=_system_prompt(_user_today()),
    retries=2,
)


# KitaruAgent(checkpoint_strategy="calls") already emits one `<tool>_tool`
# checkpoint per pydantic-ai tool call AND one `model_request` checkpoint
# per model turn. We do NOT add @kitaru.checkpoint here — nested checkpoints
# raise `Nested checkpoint calls are not supported in the Kitaru MVP`. The
# Kitaru UI groups them under the parent loseit_agent checkpoint; expand it
# in the timeline view to see the per-tool trace.


@_inner_agent.tool_plain
def search(query: str) -> str:
    """Search the Lose It! food database for candidates matching `query`."""
    return _toon(_li().search(query))


@_inner_agent.tool_plain
def describe_foods(food_ids: list[str]) -> str:
    """Inspect 1+ foods by hex food_id."""
    return _toon(_li().describe_foods(food_ids))


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
        return _toon({
            "error": "agent_guardrail_unit_conversion",
            "guidance": f"REFUSING: {serving_amount} {serving_unit} is absurdly high.",
        })
    when = date.fromisoformat(on_date) if on_date else None
    try:
        entry = _li().log_food(
            food=food_id,
            meal=meal,
            serving_amount=serving_amount,
            serving_unit=serving_unit,
            servings=servings,
            when=when,
        )
        return _toon(entry)
    except Exception as exc:
        return _toon({"error": type(exc).__name__, "message": str(exc)})


@_inner_agent.tool_plain
def diary(on_date: str | None = None) -> str:
    """Read the user's diary for a given date (default: today)."""
    when = date.fromisoformat(on_date) if on_date else None
    return _toon(_li().diary(when))


@_inner_agent.tool_plain
def whoami() -> str:
    """Print resolved Lose It! client configuration."""
    return _toon(_li().whoami())


@_inner_agent.tool_plain
@hitl_tool(question_arg="question", schema=str)
def clarify(question: str, options: list[str] | None = None) -> str:
    """Pause the flow and ask the user to disambiguate.

    Use ONLY when the request names a food generically and the choice
    materially changes calories. The flow pauses at a Kitaru wait
    condition; the FastAPI gateway resolves it via
    client.executions.input(exec_id, wait_name, user_answer).
    """


_durable_agent = KitaruAgent(
    _inner_agent,
    name="loseit-agent",
    checkpoint_strategy="calls",
    persist_message_history=True,
)


@kitaru.flow
def loseit_agent_flow(prompt: str, chat_id: str | None = None) -> str:
    """Run the loseit pydantic-ai agent as a durable Kitaru flow."""
    return _durable_agent.run_sync(prompt).output
