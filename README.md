# agent-trace-gate

**Runtime checkpoints for AI-generated code.** Track what Claude Code and
Cursor write, execute it in an instrumented sandbox, and catch hallucinated
imports, fake APIs, and schema drift with OpenTelemetry traces — before it
merges.

![gate](https://img.shields.io/badge/gate-local%20git%20hook-brightgreen)
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
   timeout, emitting `code.call` spans (per function call in Python via
   `sys.monitoring`; per entrypoint invocation in Node) — joined to the
   parent trace across the process boundary via W3C TRACEPARENT. A
   hallucinated API detonates on a visible span with the exception recorded
   at the exact frame.
5. **contract** — the return value is validated against a pydantic / zod
   contract. Code that runs clean but returns the wrong shape fails here.

## Proof, not promises

`agenttrace demo` runs eight seeded samples — a correct control plus three
planted failure classes, in both Python and Node — and **exits nonzero unless
every planted bug produces exactly the failure class it was seeded for**
(declared as `expect` in `checkpoints.toml`). Real output — the live table
adds a seeded-expectation column and Jaeger deep links, trimmed here for
width:

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

macOS / Linux:

```bash
git clone https://github.com/harshpahurkar/agent-trace-gate && cd agent-trace-gate
docker compose up -d                       # Jaeger v2 → http://localhost:16686
python3 -m venv .venv && source .venv/bin/activate
pip install -e ./checkpoints && npm ci
agenttrace demo
```

Windows (PowerShell):

```powershell
git clone https://github.com/harshpahurkar/agent-trace-gate; cd agent-trace-gate
docker compose up -d
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ./checkpoints; npm ci
agenttrace demo
```

(Or the one-shot: `.\scripts\quickstart.ps1` / `./scripts/quickstart.sh`.)
Full walkthrough with timings and what to look at in Jaeger:
**[QUICKSTART.md](QUICKSTART.md)**.

## Wiring it to your agent

The repo ships pre-wired — cloning it is the integration:

- **Claude Code** — `.claude/settings.json` enables native OTel export
  (metrics, events, beta traces → the same Jaeger) and a `PostToolUse` hook
  that records every `Edit`/`Write` to the provenance ledger.
  [docs/wiring-claude-code.md](docs/wiring-claude-code.md)
- **Cursor** — `.cursor/hooks.json` does the same via `afterFileEdit`
  (Cursor has no native OTel; hooks are its only per-action stream).
  [docs/wiring-cursor.md](docs/wiring-cursor.md)
- **The gate** — one command, no hosted CI:

  ```bash
  git config core.hooksPath .githooks
  ```

  `.githooks/pre-push` then runs `agenttrace check` over the commits leaving
  your machine and **blocks the push** on an unexpected verdict, printing
  `file:line: error-type: message` for each. Verified: a sample carrying a
  fabricated import makes `git push` exit 1 and the branch never reaches the
  remote. `--no-verify` is the documented escape hatch, and
  `./scripts/gate.sh` (or `.\scripts\gate.ps1`) runs the whole suite — seeded
  proof both ways, unit tests, ledger gate — on demand.
  [docs/local-gate.md](docs/local-gate.md)

Without `--base`, `agenttrace check` gates exactly the files the ledger says
an agent touched, carrying `agent.session_id` onto the verdict trace so you
can pivot in Jaeger between *what the agent did* and *how its code ran*.

Nothing here needs a hosted runner or a billing account. `--report ci` is
provider-agnostic: `::error` annotations plus a `$GITHUB_STEP_SUMMARY` table
if a runner happens to provide them, plain `file:line:` output everywhere
else.

## Repo map

| path | what it is |
|---|---|
| `checkpoints/` | the `agenttrace` engine (installable, `pip install -e`) |
| `runtime-node/` | Node sandbox: OTel bootstrap + instrumented harness |
| `samples/` | 8 seeded targets — each documents the failure it models |
| `checkpoints.toml` | target declarations + expected verdicts |
| `.claude/` `.cursor/` `hooks/` | agent wiring + shared provenance recorder |
| `.githooks/pre-push` | the merge gate — blocks pushes that fail a checkpoint |
| `scripts/` | quickstart, full local gate, Jaeger trace export |
| `docs/` | [architecture](docs/architecture.md) · [local gate](docs/local-gate.md) · [span dictionary](docs/span-dictionary.md) · [limitations](docs/limitations.md) · [video script](docs/video-script.md) |

## What this is not

Honest scope, spelled out in **[docs/limitations.md](docs/limitations.md)**:
the subprocess sandbox is *observation-grade containment, not a security
boundary* (truly untrusted code needs microVM/gVisor-class isolation); a
green checkpoint is not correct code (it removes one failure class, it
doesn't replace tests); a local hook is a convenience, not enforcement —
it only runs for people who installed it, and `--no-verify` skips it; and
the agent-side telemetry it integrates is partly beta and can shift.

## License

MIT
