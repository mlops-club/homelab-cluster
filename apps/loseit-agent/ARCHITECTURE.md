# loseit-agent — architecture & sequence

End state: Open WebUI on the homelab triggers a Kitaru-wrapped pydantic-ai agent that drives the `loseit` CLI. Live tool-call statuses stream back into the chat; the agent can pause for user disambiguation and resume cleanly.

## Architecture

```mermaid
flowchart LR
    classDef ext fill:#e8f4f8,stroke:#5a98b8,color:#0a3a5a
    classDef ow fill:#fff4d6,stroke:#b89a5a,color:#5a3a0a
    classDef agent fill:#e8f8e8,stroke:#5a9a5a,color:#0a5a0a
    classDef kit fill:#f4e8f8,stroke:#9a5ab8,color:#5a0a5a
    classDef model fill:#f8e8e8,stroke:#b85a5a,color:#5a0a0a

    User(["🧑 User<br/>browser"])

    subgraph cluster["homelab k8s — *.priv.mlops-club.org (Tailscale)"]
      direction LR

      subgraph owpod["chat.priv.mlops-club.org"]
        OW["Open WebUI"]
        Pipe["Pipe Function<br/>__event_emitter__"]
      end

      subgraph agentpod["loseit-agent.priv.mlops-club.org"]
        FA["FastAPI<br/>POST /run · /resume"]
        KA["KitaruAgent wrapper<br/>event_stream_handler"]
        PA["pydantic-ai Agent<br/>5 tools"]
        CLI["loseit CLI<br/>subprocess"]
      end

      subgraph kitarupod["kitaru.priv.mlops-club.org"]
        KS["Kitaru server + UI<br/>(run inspector)"]
        KDB[("SQLite metadata<br/>+ NFS artifact store")]
      end

      subgraph ollamapod["ollama.priv.mlops-club.org"]
        OL["qwen3:8b"]
      end
    end

    LI[("Lose It! API<br/>loseit.com")]

    User -- "HTTPS chat" --> OW
    OW --> Pipe
    Pipe -. "SSE stream" .-> FA
    FA --> KA
    KA --> PA
    PA -- subprocess --> CLI
    PA -- "OpenAI /v1" --> OL
    CLI -- "HTTPS + JWT" --> LI
    KA -- "checkpoints +<br/>artifacts" --> KS
    KS --- KDB
    User -. "inspect runs" .-> KS

    class User ext
    class OW,Pipe ow
    class FA,KA,PA,CLI agent
    class KS,KDB kit
    class OL,LI model
```

The Pipe lives inside the Open WebUI pod (uploaded via the admin UI; source-of-truth is `apps/loseit-agent/pipe/openwebui_pipe.py`). FastAPI + KitaruAgent + pydantic-ai + the loseit CLI are all in the agent pod. Kitaru's server + UI is a separate pod so it persists across agent restarts. All same-tailnet, all `traefik-private` ingress, all `priv-wildcard-tls`.

## Sequence — prompt → agent run → status updates → ambiguity → resume → final

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant OW as Open WebUI<br/>(Pipe)
    participant FA as FastAPI<br/>/run /resume
    participant K as KitaruAgent
    participant PA as pydantic-ai
    participant LM as qwen3:8b<br/>(Ollama)
    participant CLI as loseit CLI

    U->>OW: "log my breakfast — yogurt and some kind of berry"
    OW->>FA: POST /run {prompt}
    activate FA
    FA->>K: agent.run(prompt)
    activate K
    Note over K: opens execution<br/>checkpoint_strategy="calls"
    K->>PA: forward to wrapped Agent

    PA->>LM: chat.completions turn 1
    LM-->>PA: tool_calls: search("yogurt"), search("berry")
    K-->>FA: event: tool_start(search, "yogurt")
    FA-->>OW: SSE {kind:"tool", name:"search", args:"yogurt"}
    OW-->>U: 🟡 status: "→ search(yogurt)"
    PA->>CLI: loseit search yogurt
    CLI-->>PA: 10 candidates
    K-->>FA: event: tool_return(search ✓)
    FA-->>OW: SSE {kind:"tool_done"}
    OW-->>U: ✅ status: "→ search(yogurt) ✓"

    PA->>LM: chat.completions turn 2
    LM-->>PA: tool_calls: describe_food([3 ids])
    PA->>CLI: loseit describe-food …
    CLI-->>PA: per-serving JSON
    OW-->>U: 🟡 status: "→ describe 3 yogurt candidates"

    Note over PA,LM: model decides "berry" is ambiguous —<br/>3 plausible matches, no calorie cue

    PA->>K: kitaru.wait("clarify_berry",<br/>options=[strawberry, blueberry, raspberry])
    K-->>FA: execution paused<br/>{exec_id, wait_name, options}
    FA-->>OW: SSE {kind:"wait", exec_id, name, options}
    OW-->>U: 💬 message: "Which berry?<br/>1) strawberry  2) blueberry  3) raspberry<br/>or type your own"
    deactivate K
    deactivate FA

    Note over U,OW: chat turn ends —<br/>Pipe stores exec_id in chat metadata

    U->>OW: "blueberry"
    OW->>OW: pending exec_id found?<br/>→ route to /resume
    OW->>FA: POST /resume {exec_id, value:"blueberry"}
    activate FA
    FA->>K: client.executions.input(exec_id,<br/>"clarify_berry", "blueberry")
    activate K
    K->>PA: resume from checkpoint

    PA->>LM: chat.completions turn 3
    LM-->>PA: tool_calls: log_food(yogurt 85g),<br/>log_food(blueberry 50g)
    PA->>CLI: loseit log …
    CLI-->>PA: ✅ Logged
    K-->>FA: event: tool_return ×2
    OW-->>U: ✅ status: "log yogurt 85g (70 cal)"
    OW-->>U: ✅ status: "log blueberry 50g (28 cal)"

    PA->>LM: chat.completions turn 4
    LM-->>PA: final assistant text
    PA-->>K: result
    K-->>FA: final output + checkpoint summary
    FA-->>OW: SSE {kind:"final", text}
    deactivate K
    deactivate FA
    OW-->>U: 📝 "Logged 85g yogurt (70 cal) and<br/>50g blueberry (28 cal) → breakfast. Total 98 cal."
    OW-->>U: ⚪ status: done
```

## Key design points

- **Status emission path** = `event_stream_handler` on `KitaruAgent` → asyncio queue → SSE chunk → Open WebUI `__event_emitter__({"type":"status"})`. One pipeline, no polling.
- **Ambiguity = `kitaru.wait(name, options=…)`.** Kitaru natively pauses the execution at a checkpoint; the SSE stream emits a `wait` event, the Pipe ends its current response, and the chat turn closes.
- **Resume = same `exec_id`.** Open WebUI stores the `exec_id` in chat metadata; the user's next message goes to `POST /resume` instead of `/run`. `client.executions.input(exec_id, name, value)` unblocks the checkpoint and the run continues from where it paused (no token replay).
- **Multi-choice vs free text** are handled identically — both arrive as the user's next chat message. The Pipe just sends whatever string it receives to `/resume`. If you want strict multi-choice, validate the value server-side and re-prompt if invalid.
