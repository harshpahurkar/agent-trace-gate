# Video walkthrough — shot list

Target: ~6 minutes, screen capture + voiceover. Mirrors QUICKSTART.md so
viewers can follow along 1:1.

## Cold open (0:00–0:30)

Terminal, empty prompt.

> "19.7% of the packages LLMs import in generated code don't exist. Someone
> registers those names on PyPI — that's slopsquatting. And the APIs that do
> exist? Models invent methods on them constantly. This repo catches both at
> runtime, with OpenTelemetry traces, before the code merges. Setup is under
> five minutes — let's time it."

On-screen citation: arXiv:2406.10279 (USENIX Security '25).

## Setup (0:30–2:00)

1. `git clone … && cd agent-trace-gate`
2. `docker compose up -d` — while it pulls: "One container — Jaeger v2
   speaks OTLP natively, no collector config."
3. `pip install -e ./checkpoints && npm ci`

## The money shot (2:00–3:30)

4. `agenttrace demo` — hold on the verdict table.

> "Eight files an AI agent might hand you. Two are fine. Six are seeded with
> real failure classes — and every one is caught at exactly the checkpoint
> that should catch it. A fabricated package flagged by a live PyPI 404. A
> fake datetime method flagged by pyright. And this one — user_api — ran
> *perfectly*. Static analysis clean, no exception. It just returns the
> wrong shape. Only the contract checkpoint catches it."

5. `agenttrace demo --skip-static`

> "Turn the static net off and the same bugs detonate at runtime instead —
> watch the error move from the static checkpoints into the sandbox."

## Jaeger (3:30–4:45)

6. Open :16686 → service `agenttrace`.
   - Green `weather_report` trace: expand `code.call` spans. "These spans
     come from *inside* the sandbox subprocess — the harness joins the
     parent trace via TRACEPARENT."
   - Red `report_gen` trace: `hallucination.package` event, the 404, the
     `suggestion` attribute.
   - Red `user_api` trace: contract span, pydantic violation list.

## The agent side + CI (4:45–5:45)

7. Launch `claude` in the repo, ask it to tweak `weather_report.py`.
   Refresh Jaeger: `claude-code` and `agent-hooks` services appear.
   `agenttrace check` gates exactly the file the agent touched.
8. Cut to a GitHub PR reintroducing `_.slugify` → checkpoint-gate goes red,
   inline annotation on the exact line, verdict table in the job summary.

## Close (5:45–6:15)

> "Observation isn't isolation — the limits are documented in the repo, and
> that's deliberate. But if an AI agent writes code in your repo today, you
> can know what it imported, what it called, and what it returned — before
> you merge it. Repo's in the description."
