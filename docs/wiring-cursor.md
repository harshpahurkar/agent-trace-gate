# Wiring Cursor

Cursor has **no native OpenTelemetry export** — its enterprise audit log
covers management events (logins, membership, settings), not agent actions.
Hooks are the only first-party per-action stream, so hooks are what we use.

## The shipped config

`.cursor/hooks.json` (project-level; Cursor watches and hot-reloads it):

```json
{
  "version": 1,
  "hooks": {
    "afterFileEdit": [
      { "command": "python .cursor/hooks/record_edit.py" }
    ]
  }
}
```

`afterFileEdit` fires after the agent edits a file, delivering on stdin:

```jsonc
{
  "conversation_id": "…",   // maps to agent.session_id
  "hook_event_name": "afterFileEdit",
  "file_path": "samples/…",
  "edits": [{ "old_string": "…", "new_string": "…" }],
  "workspace_roots": ["…"], // plus model, cursor_version, user_email…
}
```

`record_edit.py` maps those fields onto the same shared recorder Claude
Code's hook uses: one ledger line in `.agent-trace/provenance.jsonl` plus one
`agent.file_edit` span (service `agent-hooks`) in Jaeger.

## Notes and limits

- `afterFileEdit` is **observe-only** — its output is ignored, so it can't
  block an edit. If you want gating *inside* Cursor, add a
  `beforeShellExecution` or `preToolUse` hook returning
  `{"permission": "deny"}`; this repo instead gates at commit/PR time with
  `agenttrace check`, which catches things a per-edit hook can't (runtime
  behaviour).
- Hook config merges across four levels (Enterprise → Team → project
  `.cursor/hooks.json` → `~/.cursor/hooks.json`); the project file shipping
  in this repo is enough for the demo.
- Cursor's **cloud agents** run command hooks from repo-root
  `.cursor/hooks.json` for most events, but a few (sessionStart/End, MCP and
  Tab hooks, workspaceOpen) don't fire in the cloud. `afterFileEdit` does.
- Hooks arrived in Cursor 1.7 (Sept 2025); if nothing fires, check the
  "Hooks" output channel and the Hooks tab under Cursor Settings →
  Customize. Reference: <https://cursor.com/docs/agent/hooks>.
