# Architecture

Four components, two trace flows, one Jaeger UI.

```
┌─────────────────────────┐          ┌──────────────────────────────┐
│  agent hook layer       │          │  checkpoint engine           │
│  .claude/ + .cursor/    │          │  checkpoints/ (agenttrace)   │
│                         │  ledger  │                              │
│  PostToolUse/           ├─────────►│  provenance → static.imports │
│  afterFileEdit          │          │  → static.types → runtime    │
│  → provenance.jsonl     │          │  .smoke → contract           │
│  → agent.file_edit span │          │  → verdict → exit code       │
└───────────┬─────────────┘          └──────────────┬───────────────┘
            │ OTLP                                  │ OTLP
            ▼                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  trace backend — Jaeger v2 (docker compose up -d)                │
│  services: claude-code · agent-hooks · agenttrace                │
└──────────────────────────────────────────────────────────────────┘
            ▲
            │ same CLI, same spans
┌───────────┴─────────────┐
│  merge gate             │
│  .githooks/pre-push     │
│  agenttrace check       │
│  --base <remote tip>    │
│  nonzero → push refused │
└─────────────────────────┘
```

## Trace flow A — observing the agent

Claude Code has native OpenTelemetry support. The repo's `.claude/settings.json`
enables it (`CLAUDE_CODE_ENABLE_TELEMETRY=1`, beta traces via
`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`) and points OTLP/gRPC at
`localhost:4317`, so simply launching `claude` inside this repo produces:

```
claude_code.interaction
  ├─ claude_code.llm_request        model, tokens, ttft_ms
  ├─ claude_code.tool  (Edit/Write) ── PostToolUse hook fires
  │                                     └─ record_edit.py → provenance ledger
  │                                        + agent.file_edit span (OTLP/JSON)
  └─ claude_code.hook               hook execution is itself traced
```

Cursor has no native OTel export, so its `afterFileEdit` hook is the whole
Cursor surface: same recorder, same ledger, same `agent.file_edit` span under
the `agent-hooks` service.

## Trace flow B — observing the agent's *output*

```
agenttrace check / demo / run
  └─ agenttrace.run {name}            root; code.provenance, agent.session_id
       ├─ checkpoint.provenance       how this file was selected
       ├─ checkpoint.static.imports   AST/specifier scan + registry oracle
       ├─ checkpoint.static.types     pyright --outputjson / tsc --noEmit
       ├─ checkpoint.runtime.smoke    python -I / node --import subprocess
       │    └─ code.call {function}   spans emitted INSIDE the sandbox,
       │                              joined via TRACEPARENT
       └─ checkpoint.contract         pydantic / zod boundary validation
```

The first failing checkpoint decides the verdict and short-circuits the rest;
skipped checkpoints still appear with `checkpoint.skipped=true` so the tree
always shows the full pipeline shape. The verdict becomes the CLI exit code,
and the CLI exit code is what `.githooks/pre-push` turns into a refused push
(see [local-gate.md](local-gate.md)).

## Correlation between the flows

The checkpoint root span carries `agent.session_id` copied from the
provenance ledger, so you can search Jaeger by session id and see both the
agent conversation trace and the runtime verdicts for the code it wrote.

Honest caveat: Claude Code does **not** propagate `OTEL_*` env vars to hook
subprocesses. When its beta tracing exports a `TRACEPARENT` to the hook, the
`agent.file_edit` span joins the agent's own trace; otherwise correlation is
by `session_id` attribute only.

## The checkpoint engine

Each checkpoint returns into a shared verdict taxonomy:

| error_type | meaning | typical evidence |
|---|---|---|
| `hallucinated-import` | package doesn't exist anywhere | `find_spec` misses + registry 404 |
| `hallucinated-api` | module is real, the member isn't | pyright `reportAttributeAccessIssue`, tsc TS2339, runtime `AttributeError` / `TypeError: x is not a function` |
| `missing-dependency` | real package, not installed here | registry 200 + not importable |
| `type-error` | static type error outside the above | other pyright/tsc errors |
| `schema-mismatch` | ran fine, wrong shape at the boundary | pydantic/zod violation list |
| `crash` | unhandled runtime exception | traceback on the failing span |
| `timeout` | exceeded the sandbox wall clock | `subprocess.TimeoutExpired` |
| `harness-error` | our tooling broke, not the sample | never blamed on the code |

Design decisions worth knowing:

- **Registry oracle is cache-first-write-through.** A committed
  `registry-cache.json` entry younger than 30 days is served without
  touching the network (deterministic CI, offline-friendly); stale or
  missing entries trigger a live fetch that rewrites the cache. Fresh
  packages (<90 days on the registry) are flagged — a "real" package that
  young matching an LLM-suggested import is what a slopsquatting trap looks
  like.
- **The sandbox joins the trace.** The runner injects the W3C `traceparent`
  of its `checkpoint.runtime.smoke` span into the child's env; the harness
  extracts it and parents its `code.call` spans there. One trace spans three
  processes.
- **Python call tracing uses `sys.monitoring`** (PEP 669, 3.12+; ~orders of
  magnitude cheaper than `sys.settrace`), filtered to the sample's own file,
  with a `sys.setprofile` fallback for 3.10/3.11. Node wraps the contract
  entrypoint in a Proxy-style traced wrapper — the same interception idea
  OTel's import-in-the-middle uses.
- **Contracts choose their own strictness.** The `user_api` contract sets
  pydantic `strict=True` because an API boundary shouldn't coerce `"42"` to
  42; the weather contract stays lax so ISO strings parse into `datetime`.
- **`demo` is the regression suite.** Every seeded sample declares `expect`
  in `checkpoints.toml`; `agenttrace demo` (and the CI seeded-proof job)
  exit nonzero unless each planted bug produces exactly its declared verdict.
