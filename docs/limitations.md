# Limitations — read this before trusting the gate

This is a demo of a *pattern*, built to be honest about where the pattern's
edges are.

## 1. This is observation, not a sandbox

`python -I` subprocesses with a stripped env and a timeout contain accidents,
not adversaries. Loader hooks, audit hooks, and profilers are all bypassable
from inside the process — Python's own docs say audit hooks are unsuitable
for sandboxing. Truly untrusted code needs container/microVM-class isolation
(gVisor, Firecracker — see E2B, Modal, llm-sandbox). The cautionary tale we
cite rather than solve: CodeRabbit's January 2025 incident, where a
`.rubocop.yml` executed Ruby *outside* the sandbox and leaked a GitHub App
key with write access to 1M+ repositories (Kudelski Security).

## 2. A green checkpoint is not correct code

The smoke run exercises the contract entrypoint's path. Hallucinations on
branches the contract never reaches, plain logic bugs, and wrong-but-
schema-valid outputs all pass. This gate removes one class of failure
(nonexistent packages/APIs, boundary schema drift). It does not replace
tests or review.

## 3. The heuristics have edges

- JS reports a missing method as `TypeError`, so the Node harness classifies
  entrypoint TypeErrors as `hallucinated-api` — a genuine argument-type bug
  lands in the same bucket.
- The Node import scanner is a specifier regex backed by `tsc`, not a full
  ES parser; dynamically-computed specifiers (`import(x + y)`) escape it.
- Private/internal packages 404 on public registries — a false positive
  until you add an allowlist. Registry flakiness is mitigated (not
  eliminated) by the committed `registry-cache.json`.

## 4. The agent-side plumbing is beta and can shift under us

Claude Code's span export needs `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`, and
`OTEL_*` vars are not propagated to hooks or Bash subprocesses — so
agent↔checkpoint correlation rests on `session_id` attributes (TRACEPARENT
joining is best-effort). Cursor has no native OTel at all; its side is
hooks-only, and `afterFileEdit` cannot block. Any release of either tool can
change these behaviours.

## 5. Version pins will age

- OTel's GenAI semantic conventions are still **Development** status and
  have already renamed attributes twice (`gen_ai.system` →
  `gen_ai.provider.name`; prompt/completion tokens → input/output tokens).
  This repo pins attribute *names*, not a schema version.
- `sys.monitoring` needs Python ≥3.12 (`sys.setprofile` fallback below).
- `@opentelemetry/sdk-node` is still 0.x with a breaking-change history.
- Jaeger v1 is EOL; this repo uses v2 (`cr.jaegertracing.io/jaegertracing/jaeger`).
