# Span dictionary

Every span, attribute, and event this repo emits. Service names in Jaeger:

| service | emitted by |
|---|---|
| `agenttrace` | the checkpoint engine + both sandbox harnesses |
| `agent-hooks` | the Claude Code / Cursor hook recorder (stdlib OTLP/JSON) |
| `claude-code` | Claude Code's own native telemetry (beta traces) |

## Service `agenttrace`

### `agenttrace.run {target}`  (root)

| attribute | example |
|---|---|
| `code.filepath` | `samples/python/hallucinated_import/report_gen.py` |
| `code.language` | `python` \| `node` |
| `code.provenance` | `seeded-sample` \| `provenance-ledger` \| `git-diff vs origin/main` |
| `agent.name` | `claude-code` \| `cursor` (when known from the ledger) |
| `agent.session_id` | the agent session that wrote the file (when known) |
| `checkpoint.verdict` | `pass` \| `fail` |
| `checkpoint.error_type` | one of the taxonomy strings |

Status is `ERROR` with the failure message when the verdict is `fail`.

### `checkpoint.provenance`

`provenance.*` attributes mirror the ledger entry (`source`, `agent`,
`session_id`).

### `checkpoint.static.imports`

| field | notes |
|---|---|
| attr `imports.total` | modules scanned |
| attr `registry.age_flag` | set when a resolvable package is <90 days old |
| event `hallucination.package` | one per unresolved import: `module`, `registry` (pypi/npm), `line`, `exists`, `age_days?`, `from_cache`, `suggestion?` |

### `checkpoint.static.types`

| field | notes |
|---|---|
| attr `checker` | `pyright` \| `tsc` |
| attr `diagnostics.errors` | error-severity count for this file |
| event `static.diagnostic` | `rule` (pyright rule or TS code), `message`, `line`, `error_type` |

### `checkpoint.runtime.smoke`

| field | notes |
|---|---|
| attr `sandbox` | `subprocess` |
| attr `timeout_seconds` | wall-clock limit |
| attr `code.calls` | traced function invocations inside the sandbox |

### `code.call {qualname}`  (children of runtime.smoke, emitted from the sandbox)

| attribute | notes |
|---|---|
| `code.function` | qualified function name |
| `code.filepath` | the sample file (only its own code is traced) |
| `code.lineno` | function's first line |

When the call raises, the exception is recorded as a span exception event and
the span status is `ERROR` — Jaeger shows the exact frame where a
hallucinated API detonated.

### `checkpoint.contract`

| field | notes |
|---|---|
| attr `contract.file` | contract path |
| event `schema.violations` | `count` + serialized pydantic `e.errors()` / zod `error.issues` |

### Skipped checkpoints

Short-circuited checkpoints still emit their span with
`checkpoint.skipped=true`, so every trace shows all five stages.

## Service `agent-hooks`

### `agent.file_edit`

| attribute | notes |
|---|---|
| `code.filepath` | repo-relative edited file |
| `agent.name` | `claude-code` \| `cursor` |
| `agent.session_id` | session/conversation id |
| `agent.tool` | `Edit` / `Write` / `afterFileEdit` |

When Claude Code's beta tracing hands the hook a `TRACEPARENT`, this span
joins the agent's own trace (same trace id, parented under the tool span);
otherwise it starts a fresh single-span trace.

## Service `claude-code`

Emitted by Claude Code itself (see [wiring-claude-code.md](wiring-claude-code.md)):
`claude_code.interaction` → `claude_code.llm_request`, `claude_code.tool`
(with `.blocked_on_user` / `.execution` children), `claude_code.hook`.
These names are Anthropic's, documented at
<https://code.claude.com/docs/en/monitoring-usage>, and require
`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`.
