# Wiring Claude Code

Everything here ships in the repo's `.claude/settings.json` — cloning the
repo *is* the wiring. This page explains each line so you can lift it into
your own projects.

## Telemetry env block

```jsonc
"env": {
  "CLAUDE_CODE_ENABLE_TELEMETRY": "1",        // master switch — nothing exports without it
  "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1", // beta: spans (claude_code.interaction > llm_request/tool/hook)
  "OTEL_METRICS_EXPORTER": "otlp",            // claude_code.* metrics (tokens, cost, lines of code…)
  "OTEL_LOGS_EXPORTER": "otlp",               // events (user_prompt, tool_result, api_request…)
  "OTEL_TRACES_EXPORTER": "otlp",             // the beta trace stream
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",  // Jaeger v2 from docker-compose.yml
  "OTEL_METRIC_EXPORT_INTERVAL": "10000",     // default is 60 s; 10 s is nicer for demos
  "OTEL_LOGS_EXPORT_INTERVAL": "5000"
}
```

Launch `claude` inside the repo (with `docker compose up -d` running) and the
Jaeger service dropdown gains **claude-code**. The span hierarchy you'll see:

```
claude_code.interaction
  ├─ claude_code.llm_request   model, input/output/cache tokens, ttft_ms
  ├─ claude_code.tool          one per tool call
  │    ├─ claude_code.tool.blocked_on_user
  │    └─ claude_code.tool.execution
  └─ claude_code.hook          hook_event, hook_name (e.g. PostToolUse:Edit)
```

Content (prompts, responses, tool payloads) is **redacted by default**;
opt-in vars exist (`OTEL_LOG_USER_PROMPTS=1`, `OTEL_LOG_TOOL_DETAILS=1`, …)
if you want it. Reference: <https://code.claude.com/docs/en/monitoring-usage>.

## The provenance hook

```jsonc
"hooks": {
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/record_edit.py\"",
      "timeout": 20
    }]
  }]
}
```

After every successful `Edit`/`Write`, Claude Code pipes a JSON payload
(`session_id`, `tool_name`, `tool_input.file_path`, …) into the hook's stdin.
`record_edit.py` appends one line to `.agent-trace/provenance.jsonl` and
POSTs a single `agent.file_edit` span. That ledger is what makes
`agenttrace check` gate *exactly* the files an agent touched.

The hook always exits 0 — provenance must never block the agent.

## Caveats we designed around (worth knowing)

1. **`OTEL_*` env vars are not propagated to hook subprocesses** (or Bash
   tool subprocesses). The hook therefore uses stdlib `urllib` to POST
   OTLP/JSON to a hardcoded-default `http://localhost:4318`, overridable via
   `AGENTTRACE_HOOK_OTLP`.
2. **Trace export is beta** and requires `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`.
   Metrics and events work without it.
3. **Correlation is session-first.** When beta tracing propagates a W3C
   `TRACEPARENT` into the hook, the `agent.file_edit` span joins the agent's
   trace; otherwise you correlate agent activity ↔ checkpoint verdicts by the
   `agent.session_id` attribute both sides carry.
4. Project-scoped `.claude/settings.json` is shareable by design, but Claude
   Code will ask you to trust project settings on first use — that's expected.
