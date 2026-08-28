"""agenttrace CLI.

    agenttrace demo    run every target in checkpoints.toml and assert each
                       seeded sample produces exactly the failure it models —
                       the repo's living proof that the pipeline catches what
                       it claims to catch (exit 0 only when all match)
    agenttrace check   gate mode: resolve AI-authored files from the
                       provenance ledger (or a --base git diff, which is what
                       the pre-push hook uses), run the pipeline, exit 1 on any
                       unexpected verdict — or 2 if the range would not resolve
                       and no checkpoint ever ran
    agenttrace run     run the pipeline over one file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, config, otel, pipeline, provenance, report
from .config import Target


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--otel", choices=["auto", "otlp", "console", "off"], default="auto",
                        help="span export mode (default: auto-detect the OTLP endpoint)")
    parser.add_argument("--skip-static", action="store_true",
                        help="skip static checkpoints — lets seeded bugs detonate at runtime instead")
    parser.add_argument("--report", choices=["console", "ci"], default="console",
                        help="ci adds one machine-readable line per failure "
                             "(::error annotations inside GitHub Actions, file:line elsewhere)")


def _finish(verdicts, args, *, show_expected: bool, ok: bool) -> int:
    otel.flush()
    report.print_table(verdicts, show_expected=show_expected)
    if args.report == "ci":
        report.ci_annotations(verdicts)
        report.ci_summary(verdicts, show_expected=show_expected)
    return 0 if ok else 1


def cmd_demo(args) -> int:
    cfg = config.load()
    otel.configure(args.otel)
    verdicts = [
        pipeline.run_target(cfg, t, skip_static=args.skip_static)
        for t in cfg.targets
    ]
    ok = all(v.as_expected for v in verdicts)
    code = _finish(verdicts, args, show_expected=True, ok=ok)
    if ok:
        report.console.print(
            f"[green]all {len(verdicts)} targets behaved exactly as seeded - "
            "every planted bug was caught at the expected checkpoint[/green]"
        )
    else:
        report.console.print("[red]seeded expectations not met - the pipeline missed something[/red]")
    return code


def cmd_check(args) -> int:
    cfg = config.load()
    otel.configure(args.otel)

    if args.base:
        try:
            changed = set(config.changed_files(cfg.root, args.base, args.head))
        except config.GitRangeError as exc:
            report.console.print(f"[red]gate could not run:[/red] {exc}")
            report.console.print(
                "[yellow]no checkpoint ran - this is a harness problem, "
                "not a verdict about the code being pushed.[/yellow]"
            )
            return 2
        candidates = [t for t in cfg.targets if t.file in changed]
        source = {"source": f"git-diff {config.diff_spec(cfg.root, args.base, args.head)}"}
        prov_by_file: dict[str, dict] = {}
    else:
        ledger = provenance.read_ledger(cfg.root)
        candidates = [t for t in cfg.targets if t.file in ledger]
        source = {"source": "provenance-ledger"}
        prov_by_file = ledger

    if not candidates:
        report.console.print(
            "[yellow]no AI-authored target files to gate[/yellow] "
            f"({source['source']}; {len(cfg.targets)} targets declared)"
        )
        return 0

    verdicts = []
    for t in candidates:
        entry = prov_by_file.get(t.file, {})
        prov = {**source, "agent": entry.get("agent"), "session_id": entry.get("session_id")}
        verdicts.append(pipeline.run_target(cfg, t, skip_static=args.skip_static, provenance=prov))

    # gate rule: seeded targets must land exactly on their declared expectation;
    # anything without an expectation must simply pass
    ok = all(v.as_expected for v in verdicts)
    return _finish(verdicts, args, show_expected=True, ok=ok)


def cmd_run(args) -> int:
    file = Path(args.file).resolve()
    cfg = config.load(config.find_root(file.parent))
    otel.configure(args.otel)

    target = cfg.target_for(file)
    if target is None:
        language = args.language or ("node" if file.suffix in (".mjs", ".cjs", ".js", ".ts") else "python")
        target = Target(
            name=file.stem,
            file=file.relative_to(cfg.root).as_posix(),
            language=language,
            contract=args.contract,
        )
    verdict = pipeline.run_target(cfg, target, skip_static=args.skip_static)
    return _finish([verdict], args, show_expected=False, ok=verdict.passed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agenttrace",
        description="Runtime checkpoints for AI-generated code, traced with OpenTelemetry.",
    )
    parser.add_argument("--version", action="version", version=f"agenttrace {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="run all seeded samples and assert every planted bug is caught")
    _common(p_demo)
    p_demo.set_defaults(fn=cmd_demo)

    p_check = sub.add_parser(
        "check", help="gate AI-authored files (provenance ledger, or --base for a diff)"
    )
    p_check.add_argument("--base", help="git ref to diff against, e.g. origin/main")
    p_check.add_argument("--head", default="HEAD",
                         help="tip of the range being gated (default: HEAD)")
    _common(p_check)
    p_check.set_defaults(fn=cmd_check)

    p_run = sub.add_parser("run", help="run the checkpoint pipeline over one file")
    p_run.add_argument("file")
    p_run.add_argument("--contract", help="contract file (repo-relative)")
    p_run.add_argument("--language", choices=["python", "node"])
    _common(p_run)
    p_run.set_defaults(fn=cmd_run)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
