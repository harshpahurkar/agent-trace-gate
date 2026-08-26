# The local gate

This repo has **no hosted CI**. The merge gate is a git hook, so it costs
nothing, needs no account, and runs identically on every machine that clones
the repo.

## Install (one command)

```bash
git config core.hooksPath .githooks
```

That points git at the versioned `.githooks/` directory. Nothing is copied,
so the hook updates when the repo does.

## What it does

`.githooks/pre-push` runs before every push:

1. git hands it each ref being pushed as
   `<local ref> <local oid> <remote ref> <remote oid>`.
2. The base is the remote's current tip — everything the remote already has.
   For a brand-new branch it falls back to `origin/main` (then `main`,
   `origin/master`, `master`).
3. It runs `agenttrace check --base <base> --head <local oid> --report ci`,
   which gates exactly the watched files in that range.
4. Non-matching verdict → nonzero exit → **the push is blocked**, with one
   `file:line: error-type: message` line per failure.

Because the gate runs on the commits leaving your machine, "before it merges
to main" is enforced at the last moment it can be enforced locally.

## Bypass

```bash
git push --no-verify
```

Standard git escape hatch. Use it when you're pushing a work-in-progress
branch on purpose; it is deliberately not a secret.

## Full local run

The pre-push hook is deliberately narrow (only the diff). To run everything a
CI job would have:

```bash
./scripts/gate.sh          # macOS / Linux / Git Bash
.\scripts\gate.ps1         # Windows PowerShell
```

That runs the seeded proof both ways (static + `--skip-static` runtime
detonation), the unit tests, and the ledger gate, and exits nonzero if any of
them fail.

## What "expected" means

`agenttrace check` does not simply demand that everything passes. Each target
in `checkpoints.toml` may declare `expect`, and the gate compares the
*outcome* against it:

- seeded samples declare their planted failure (`expect = "hallucinated-import"`),
  so they gate green while they keep failing the way they're supposed to;
- real files omit `expect`, so anything other than a clean pass blocks.

This is why the same command works as both the demo's proof and a real gate:
it asserts *declared* behaviour, not blanket success.

## If you do have hosted CI

Nothing here is GitHub-specific, and `--report ci` auto-detects: inside
GitHub Actions it emits `::error` workflow commands and writes the verdict
table to `$GITHUB_STEP_SUMMARY`; anywhere else (a hook, a bare shell, GitLab,
Forgejo, Jenkins) it prints plain `file:line:` lines. Wiring this into a
hosted runner is three steps — install Python + Node deps, `docker compose up
-d jaeger`, then `agenttrace check --base origin/<base> --report ci` — but
none of that is required, and this repo ships without it on purpose.

## Honest limitation

A local hook is a *convenience*, not an enforcement boundary: it only runs
for people who ran the install command, and `--no-verify` skips it. Real
enforcement needs something server-side that the pusher cannot skip (a
protected branch with a required check, or a server-side `pre-receive` hook).
See [limitations.md](limitations.md).
