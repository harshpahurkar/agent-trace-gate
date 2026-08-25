"""Render verdicts: console table, CI annotations, job summary."""

from __future__ import annotations

import io
import os
import sys

from rich.console import Console
from rich.table import Table

from . import otel
from .verdict import Verdict


def _safe_console() -> Console:
    """A console that degrades instead of crashing on a non-UTF-8 stdout.

    Git hooks routinely run with a legacy Windows console (cp1252), which
    cannot encode box-drawing characters — an unencodable glyph would
    otherwise raise UnicodeEncodeError mid-table and take the gate down with
    it. Table cells stay ASCII for the same reason.
    """
    stream = sys.stdout
    encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
    if encoding != "utf8":
        try:
            stream = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding=getattr(sys.stdout, "encoding", None) or "utf-8",
                errors="replace",
                line_buffering=True,
            )
        except (AttributeError, ValueError):
            stream = sys.stdout
    return Console(file=stream)


console = _safe_console()


def print_table(verdicts: list[Verdict], show_expected: bool = False) -> None:
    # every column folds rather than ellipsizing: rich's truncation marker is
    # non-ASCII and turns to mojibake on the legacy consoles git hooks get
    table = Table(title="agenttrace verdicts", title_justify="left")
    table.add_column("sample", style="bold", overflow="fold")
    table.add_column("lang", overflow="fold")
    table.add_column("verdict", overflow="fold")
    table.add_column("caught by", overflow="fold")
    table.add_column("error type", overflow="fold")
    table.add_column("detail", max_width=58, overflow="fold")
    if show_expected:
        table.add_column("seeded", overflow="fold")
    if otel.exporting():
        table.add_column("trace", overflow="fold")

    for v in verdicts:
        cells = [
            v.name,
            "py" if v.language == "python" else "js",
            "[green]PASS[/green]" if v.passed else "[red]FAIL[/red]",
            (v.checkpoint or "-").removeprefix("checkpoint."),
            v.error_type or "-",
            v.message or "-",
        ]
        if show_expected:
            mark = "[green]as seeded[/green]" if v.as_expected else "[red]UNEXPECTED[/red]"
            cells.append(f"{v.expected or 'pass'} {mark}")
        if otel.exporting():
            cells.append(
                f"[link={otel.jaeger_link(v.trace_id)}]{v.trace_id[:12]}[/link]" if v.trace_id else "-"
            )
        table.add_row(*cells)
    console.print(table)

    if not otel.exporting():
        console.print(
            f"[dim]spans not exported - no OTLP endpoint at {otel.endpoint()} "
            "(start one with `docker compose up -d`)[/dim]"
        )


def ci_annotations(verdicts: list[Verdict]) -> None:
    """One machine-readable line per failure.

    Inside GitHub Actions these are `::error` workflow commands that render as
    inline annotations; everywhere else (a git hook, a bare shell, any other
    runner) they degrade to plain `file:line: message`, which editors and
    terminals already know how to jump to.
    """
    in_gha = os.environ.get("GITHUB_ACTIONS") == "true"
    for v in verdicts:
        if v.passed:
            continue
        message = v.message.replace("\n", " ")
        if in_gha:
            location = f"file={v.file}" + (f",line={v.line}" if v.line else "")
            print(f"::error {location},title=agenttrace {v.error_type}::{message}")
        else:
            location = f"{v.file}:{v.line}" if v.line else v.file
            print(f"{location}: {v.error_type}: {message}")


def ci_summary(verdicts: list[Verdict], show_expected: bool = False) -> None:
    """Markdown verdict table, written to $GITHUB_STEP_SUMMARY when a runner
    provides one. No-op otherwise — the console table already covered it."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = ["## agenttrace verdicts", ""]
    header = "| sample | lang | verdict | caught by | error type | detail |"
    divider = "|---|---|---|---|---|---|"
    if show_expected:
        header += " seeded expectation |"
        divider += "---|"
    lines += [header, divider]
    for v in verdicts:
        row = "| {} | {} | {} | {} | {} | {} |".format(
            v.name,
            v.language,
            "✅ pass" if v.passed else "❌ fail",
            (v.checkpoint or "—").removeprefix("checkpoint."),
            v.error_type or "—",
            (v.message or "—").replace("|", "\\|"),
        )
        if show_expected:
            row += " {} {} |".format(v.expected or "pass", "as seeded" if v.as_expected else "**UNEXPECTED**")
        lines.append(row)
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n\n")
