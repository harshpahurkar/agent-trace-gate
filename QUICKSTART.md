# Quickstart — runtime checkpoints in under 5 minutes

Prerequisites: Docker running, Python 3.10+ (3.12 recommended), Node 20.6+,
git. Timings below were measured cold on a mid-range Windows 11 laptop; warm
numbers in parentheses.

**Windows one-shot:** `.\scripts\quickstart.ps1` &nbsp;·&nbsp;
**macOS/Linux one-shot:** `./scripts/quickstart.sh` — both collapse steps 2–4.

## 1. Clone (~15 s)

```bash
git clone https://github.com/harshpahurkar/agent-trace-gate
cd agent-trace-gate
```

## 2. Start the trace backend (~90 s first pull, 3 s after)

```bash
docker compose up -d
```

One container: Jaeger v2, which speaks OTLP natively — no collector config.
UI comes up at <http://localhost:16686>.

## 3. Install the engine (~90 s, once)

macOS / Linux:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ./checkpoints
npm ci
```

Windows (PowerShell):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ./checkpoints
npm ci
```

Activating the venv is what puts the `agenttrace` command on PATH for the
next step. In a fresh shell later, re-activate — or call it by path
(`./.venv/bin/agenttrace` / `.\.venv\Scripts\agenttrace`).

## 4. Run the seeded demo (~60 s first run while pyright bootstraps, ~10 s after)

```bash
agenttrace demo
```

You get eight verdicts — two clean controls and six seeded failures, each
producing exactly the failure class it was planted for (in this default run,
caught at the checkpoint that models it). The live table also shows the
seeded-expectation check and Jaeger deep links, trimmed here for width:

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

Exit code 0 means every planted bug was caught as declared — `demo` is also
the engine's regression suite.

## 5. Look at a trace (~45 s)

Open <http://localhost:16686>, pick service **agenttrace**:

- the red `report_gen` trace → `checkpoint.static.imports` carries a
  `hallucination.package` event with the live PyPI 404;
- the green `weather_report` trace → `code.call summarize` /
  `code.call build_report` spans with real durations, emitted from inside
  the sandbox subprocess and joined to the parent trace via TRACEPARENT;
- the red `user_api` trace → everything green until
  `checkpoint.contract`, which lists the pydantic violations.

That's the whole loop: **~4–5 minutes cold, under a minute warm.**

---

## Beyond the five minutes

- **See the failures detonate at runtime instead:**
  `agenttrace demo --skip-static` — the same bugs now surface as
  `ModuleNotFoundError` / `AttributeError` / `TypeError` exception events on
  `code.call` spans.
- **Trace the agent itself:** launch `claude` inside this repo — the shipped
  `.claude/settings.json` turns on Claude Code's native OTel export, and the
  Jaeger service dropdown grows a `claude-code` entry next to `agenttrace`.
  Details: [docs/wiring-claude-code.md](docs/wiring-claude-code.md).
- **Cursor:** the shipped `.cursor/hooks.json` records every agent file edit
  to the provenance ledger and Jaeger. Details:
  [docs/wiring-cursor.md](docs/wiring-cursor.md).
- **Gate your own edits:** after an agent edits a watched file,
  `agenttrace check` gates exactly the files in the ledger.
- **Turn on the merge gate:** `git config core.hooksPath .githooks` — from
  then on `git push` runs the checkpoints over the outgoing commits and
  refuses the push on an unexpected verdict. No hosted CI, no billing
  account. See [docs/local-gate.md](docs/local-gate.md).
- **Metrics too:** `docker compose down && docker compose --profile lgtm up -d lgtm`
  swaps Jaeger for Grafana's OTel-LGTM all-in-one (UI on :3000, admin/admin)
  so Claude Code's `claude_code.*` metrics have somewhere to land.
