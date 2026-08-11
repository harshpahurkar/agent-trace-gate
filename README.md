# agent-trace-gate

**Runtime checkpoints for AI-generated code.** Track what Claude Code and
Cursor write, execute it in an instrumented sandbox, and catch hallucinated
imports, fake APIs, and schema drift with OpenTelemetry traces — before it
merges.

[![checkpoint-gate](https://github.com/harshpahurkar/agent-trace-gate/actions/workflows/checkpoint-gate.yml/badge.svg)](https://github.com/harshpahurkar/agent-trace-gate/actions/workflows/checkpoint-gate.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![node](https://img.shields.io/badge/node-20.6%2B-green)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

## Why

- **19.7% of packages referenced in LLM-generated code don't exist** —
  205,474 unique fabricated names across 576k samples ([USENIX Security '25,
  arXiv:2406.10279](https://arxiv.org/abs/2406.10279)). Attackers register
  those exact names ("[slopsquatting](https://en.wikipedia.org/wiki/Slopsquatting)"):
  one researcher's fake `huggingface-cli` drew 15,000+ real downloads.
- **APIs get invented too** — hallucination rates hit ~85% for
  project-specific APIs ([arXiv:2505.05057](https://arxiv.org/abs/2505.05057)).
- **LLM observability tools trace the *agent*** (tokens, cost, tool calls) —
  OpenLLMetry, Langfuse, LangSmith, Claude Code's own OTel export. **None of
  them trace the *execution of the code the agent wrote*, or gate CI on it.**
  That's the gap this repo demonstrates.

## What it does

```
agent writes code ──► provenance hooks ──► checkpoint pipeline ──► verdict ──► CI gate
 (Claude Code /       (.agent-trace/        every stage is an      exit code    merge
  Cursor hooks)        provenance.jsonl)    OpenTelemetry span                  blocked
```

Five checkpoints per file, one trace per run, visible in Jaeger:

1. **provenance** — was this file written by an agent, in which session?
2. **static.imports** — AST/specifier scan; unresolved names are checked
   against PyPI/npm. A 404 is a hallucinated dependency; a package younger
   than 90 days gets a slopsquatting flag.
3. **static.types** — `pyright --outputjson` / `tsc --noEmit` mapped onto a
   shared error taxonomy.
4. **runtime.smoke** — the differentiator: the code actually *runs*, in a
   `python -I` / `node --import` subprocess with a stripped env and a
   timeout, emitting a `code.call` span per function — joined to the parent
   trace across the process boundary via W3C TRACEPARENT. A hallucinated API
   detonates on a visible span with the exception recorded at the exact frame.
5. **contract** — the return value is validated against a pydantic / zod
   contract. Code that runs clean but returns the wrong shape fails here.

## Proof, not promises

`agenttrace demo` runs eight seeded samples — a correct control plus three
planted failure classes, in both Python and Node — and **exits nonzero unless
every planted bug is caught at exactly the checkpoint it was seeded for**.
Real output:

```
sample          lang  verdict  caught by       error type           detail
weather_report  py    PASS     —               —                    —
report_gen      py    FAIL     static.imports  hallucinated-import  package 'pandas_profiling_lite' does not exist on pypi
date_utils      py    FAIL     static.types    hallucinated-api     Cannot access attribute "from_iso" for class "type[datetime]"
user_api        py    FAIL     contract        schema-mismatch      2 contract violation(s)
invoice_ok      js    PASS     —               —                    —
fetch_prices    js    FAIL     static.imports  hallucinated-import  package 'axios-scraper' does not exist on npm
slugify         js    FAIL     static.types    hallucinated-api     TS2339: Property 'slugify' does not exist on type 'LoDashStatic'
invoice         js    FAIL     contract        schema-mismatch      1 contract violation(s)
```

Run `agenttrace demo --skip-static` and the same bugs detonate at *runtime*
instead — `ModuleNotFoundError`, `AttributeError`, `TypeError` — each
recorded as an exception event on the `code.call` span where it happened.
The `user_api`/`invoice` samples are the sneaky ones: clean static analysis,
clean execution, wrong shape — only the contract checkpoint catches them.

## Quickstart (~4–5 minutes cold)

```bash
git clone https://github.com/harshpahurkar/agent-trace-gate && cd agent-trace-gate
docker compose up -d                      # Jaeger v2 → http://localhost:16686
python -m venv .venv && .venv/Scripts/pip install -e ./checkpoints   # or ./.venv/bin/pip
npm ci
agenttrace demo
```

Windows one-shot: `.\scripts\quickstart.ps1`. Full walkthrough with timings
and what to look at in Jaeger: **[QUICKSTART.md](QUICKSTART.md)**.

## Wiring it to your agent

The repo ships pre-wired — cloning it is the integration:

- **Claude Code** — `.claude/settings.json` enables native OTel export
  (metrics, events, beta traces → the same Jaeger) and a `PostToolUse` hook
  that records every `Edit`/`Write` to the provenance ledger.
  [docs/wiring-claude-code.md](docs/wiring-claude-code.md)
- **Cursor** — `.cursor/hooks.json` does the same via `afterFileEdit`
  (Cursor has no native OTel; hooks are its only per-action stream).
  [docs/wiring-cursor.md](docs/wiring-cursor.md)
- **CI** — `agenttrace check --base origin/main` gates the PR diff:
  inline `::error` annotations on the offending line, a verdict table in the
  job summary, raw Jaeger traces as a build artifact. Add the
  `checkpoint-gate` workflow to branch protection and hallucinations can't
  land on main.

Locally, `agenttrace check` (no flags) gates exactly the files the ledger
says an agent touched, carrying `agent.session_id` onto the verdict trace so
you can pivot in Jaeger between *what the agent did* and *how its code ran*.

## Repo map

| path | what it is |
|---|---|
| `checkpoints/` | the `agenttrace` engine (installable, `pip install -e`) |
| `runtime-node/` | Node sandbox: OTel bootstrap + instrumented harness |
| `samples/` | 8 seeded targets — each documents the failure it models |
| `checkpoints.toml` | target declarations + expected verdicts |
| `.claude/` `.cursor/` `hooks/` | agent wiring + shared provenance recorder |
| `.github/workflows/` | seeded-proof job + PR merge gate |
| `docs/` | [architecture](docs/architecture.md) · [span dictionary](docs/span-dictionary.md) · [limitations](docs/limitations.md) · [video script](docs/video-script.md) |

## What this is not

Honest scope, spelled out in **[docs/limitations.md](docs/limitations.md)**:
the subprocess sandbox is *observation-grade containment, not a security
boundary* (truly untrusted code needs microVM/gVisor-class isolation); a
green checkpoint is not correct code (it removes one failure class, it
doesn't replace tests); and the agent-side telemetry it integrates is
partly beta and can shift.

## License

MIT
