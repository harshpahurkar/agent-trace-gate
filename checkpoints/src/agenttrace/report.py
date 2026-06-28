"""Render verdicts: console table, GitHub job summary, ::error annotations."""

from __future__ import annotations

import os

from rich.console import Console
from rich.table import Table

from . import otel
from .verdict import Verdict

console = Console()


def print_table(verdicts: list[Verdict], show_expected: bool = False) -> None:
    table = Table(title="agenttrace verdicts", title_justify="left")
    table.add_column("sample", style="bold")
    table.add_column("lang")
    table.add_column("verdict")
    table.add_column("caught by")
    table.add_column("error type")
    table.add_column("detail", max_width=58, overflow="fold")
    if show_expected:
        table.add_column("seeded expectation")
    if otel.exporting():
        table.add_column("trace")

    for v in verdicts:
        cells = [
            v.name,
            "py" if v.language == "python" else "js",
            "[green]PASS[/green]" if v.passed else "[red]FAIL[/red]",
            (v.checkpoint or "—").removeprefix("checkpoint."),
            v.error_type or "—",
            v.message or "—",
        ]
        if show_expected:
            mark = "[green]✓ as seeded[/green]" if v.as_expected else "[red]✗ UNEXPECTED[/red]"
            cells.append(f"{v.expected or 'pass'} {mark}")
        if otel.exporting():
            cells.append(f"[link={otel.jaeger_link(v.trace_id)}]{v.trace_id[:12]}…[/link]" if v.trace_id else "—")
        table.add_row(*cells)
    console.print(table)

    if not otel.exporting():
        console.print(
            f"[dim]spans not exported — no OTLP endpoint at {otel.endpoint()} "
            "(start one with `docker compose up -d`)[/dim]"
        )


def github_annotations(verdicts: list[Verdict]) -> None:
    """Workflow-command lines that render as inline file annotations on the PR."""
    for v in verdicts:
        if v.passed:
            continue
        location = f"file={v.file}" + (f",line={v.line}" if v.line else "")
        message = v.message.replace("\n", " ")
        print(f"::error {location},title=agenttrace {v.error_type}::{message}")


def github_summary(verdicts: list[Verdict], show_expected: bool = False) -> None:
    """Markdown verdict table for $GITHUB_STEP_SUMMARY."""
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
            row += " {} {} |".format(v.expected or "pass", "✓" if v.as_expected else "✗ UNEXPECTED")
        lines.append(row)
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n\n")
