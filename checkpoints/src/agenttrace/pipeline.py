"""The checkpoint pipeline: five named checkpoints, one trace per target file.

    agenttrace.run {name}                 root span
      ├─ checkpoint.provenance            who wrote this file (ledger/diff/seeded)
      ├─ checkpoint.static.imports        AST/specifier scan + registry oracle
      ├─ checkpoint.static.types          pyright --outputjson / tsc --noEmit
      ├─ checkpoint.runtime.smoke         sandboxed instrumented execution
      │    └─ code.call {fn}...           spans emitted by the harness subprocess
      └─ checkpoint.contract              pydantic / zod boundary validation

The first failing checkpoint decides the verdict and short-circuits the rest;
skipped checkpoints still appear in the trace with checkpoint.skipped=true so
the Jaeger tree always shows the full pipeline shape.
"""

from __future__ import annotations

import difflib
from importlib import metadata
from pathlib import Path

from opentelemetry import trace as ot_trace

from . import otel
from . import verdict as V
from .config import Config, Target
from .static_checks import node_imports, py_imports, pyright_gate, registry, tsc_gate

_STATIC_PRIORITY = {V.HALLUCINATED_IMPORT: 0, V.HALLUCINATED_API: 1, V.TYPE_ERROR: 2}


def _suggestion(name: str, language: str) -> str | None:
    """Closest installed package to a hallucinated name, for the fix hint."""
    if language == "python":
        try:
            candidates = set(metadata.packages_distributions())
        except Exception:
            candidates = set()
    else:
        candidates = set(node_imports.builtin_modules())
    close = difflib.get_close_matches(name, candidates, n=1, cutoff=0.75)
    return close[0] if close else None


def _skip(tracer, parent_ctx, names: list[str]) -> None:
    for name in names:
        span = tracer.start_span(name, context=parent_ctx)
        span.set_attribute("checkpoint.skipped", True)
        span.end()


def run_target(
    cfg: Config,
    target: Target,
    *,
    skip_static: bool = False,
    provenance: dict | None = None,
) -> V.Verdict:
    tracer = otel.tracer()
    sample = (cfg.root / target.file).resolve()
    contract = (cfg.root / target.contract).resolve() if target.contract else None

    result = V.Verdict(
        name=target.name, file=target.file, language=target.language, expected=target.expect
    )

    with tracer.start_as_current_span(f"agenttrace.run {target.name}") as root:
        result.trace_id = f"{root.get_span_context().trace_id:032x}"
        root.set_attribute("code.filepath", target.file)
        root.set_attribute("code.language", target.language)
        root.set_attribute("code.provenance", (provenance or {}).get("source", "seeded-sample"))
        if provenance and provenance.get("agent"):
            root.set_attribute("agent.name", provenance["agent"])
        if provenance and provenance.get("session_id"):
            root.set_attribute("agent.session_id", provenance["session_id"])

        parent_ctx = ot_trace.set_span_in_context(root)
        remaining = list(V.CHECKPOINTS)

        def decide(checkpoint: str, error_type: str, message: str, detail=None, line=None):
            result.verdict = "fail"
            result.error_type = error_type
            result.checkpoint = checkpoint
            result.message = message
            result.detail = detail or {}
            result.line = line

        # ---- checkpoint.provenance -------------------------------------
        remaining.remove("checkpoint.provenance")
        with tracer.start_as_current_span("checkpoint.provenance") as span:
            for key, value in (provenance or {"source": "seeded-sample"}).items():
                if value is not None:
                    span.set_attribute(f"provenance.{key}", str(value))
            # A declared target that isn't on disk is a config problem, not a
            # defect in the code under test — so it is harness-error, never
            # crash. Catching it here also stops one renamed file from taking
            # down the whole gate with an uncaught FileNotFoundError.
            if not sample.is_file():
                decide("checkpoint.provenance", V.HARNESS_ERROR,
                       f"declared target is missing from disk: {target.file}",
                       {"file": target.file})
                span.set_status(ot_trace.Status(ot_trace.StatusCode.ERROR, result.message))

        # ---- checkpoint.static.imports ---------------------------------
        if result.passed and not skip_static:
            remaining.remove("checkpoint.static.imports")
            with tracer.start_as_current_span("checkpoint.static.imports") as span:
                source = sample.read_text(encoding="utf-8")
                if target.language == "python":
                    found = py_imports.check_file(source, str(sample))
                    ecosystem = "pypi"
                else:
                    found = node_imports.check_file(source, cfg.root)
                    ecosystem = "npm"
                span.set_attribute("imports.total", len(found))

                for imp in found:
                    if imp.resolution != "unknown":
                        continue
                    reg = registry.check(imp.module, ecosystem, cfg.root)
                    attrs = {
                        "module": imp.module,
                        "registry": ecosystem,
                        "line": imp.line,
                        "exists": str(reg.exists),
                        "from_cache": reg.from_cache,
                    }
                    if reg.age_days is not None:
                        attrs["age_days"] = reg.age_days
                    hint = _suggestion(imp.module, target.language)
                    if hint:
                        attrs["suggestion"] = hint
                    span.add_event("hallucination.package", attrs)

                    if reg.exists is False:
                        msg = f"package '{imp.module}' does not exist on {ecosystem}"
                        if hint:
                            msg += f" (closest installed: {hint})"
                        decide("checkpoint.static.imports", V.HALLUCINATED_IMPORT, msg,
                               {"module": imp.module, "registry": ecosystem}, line=imp.line)
                    elif reg.exists is True:
                        msg = f"'{imp.module}' exists on {ecosystem} but is not installed here"
                        if reg.young:
                            msg += f" — registered only {reg.age_days} days ago (slopsquatting signal)"
                            span.set_attribute("registry.age_flag", True)
                        decide("checkpoint.static.imports", V.MISSING_DEPENDENCY, msg,
                               {"module": imp.module}, line=imp.line)
                    else:
                        decide("checkpoint.static.imports", V.MISSING_DEPENDENCY,
                               f"'{imp.module}' is not importable and the {ecosystem} registry "
                               "is unreachable — cannot rule out a hallucination",
                               {"module": imp.module, "registry_unreachable": True}, line=imp.line)
                    break  # first bad import decides
                if not result.passed:
                    span.set_status(ot_trace.Status(ot_trace.StatusCode.ERROR, result.message))

        # ---- checkpoint.static.types -----------------------------------
        if result.passed and not skip_static:
            remaining.remove("checkpoint.static.types")
            with tracer.start_as_current_span("checkpoint.static.types") as span:
                try:
                    if target.language == "python":
                        diags = pyright_gate.run(sample)
                        span.set_attribute("checker", "pyright")
                    else:
                        diags = tsc_gate.run(sample, cfg.root)
                        span.set_attribute("checker", "tsc")
                except Exception as exc:
                    diags = []
                    decide("checkpoint.static.types", V.HARNESS_ERROR, f"static checker failed: {exc}")
                span.set_attribute("diagnostics.errors", len(diags))
                for diag in diags:
                    span.add_event(
                        "static.diagnostic",
                        {
                            "rule": getattr(diag, "rule", None) or getattr(diag, "code", ""),
                            "message": diag.short(),
                            "line": diag.line,
                            "error_type": diag.error_type,
                        },
                    )
                if diags and result.passed:
                    worst = min(diags, key=lambda d: _STATIC_PRIORITY.get(d.error_type, 9))
                    decide("checkpoint.static.types", worst.error_type, worst.short(),
                           {"diagnostics": len(diags)}, line=worst.line)
                if not result.passed:
                    span.set_status(ot_trace.Status(ot_trace.StatusCode.ERROR, result.message))

        # ---- checkpoint.runtime.smoke + checkpoint.contract ------------
        if result.passed:
            remaining.remove("checkpoint.runtime.smoke")
            with tracer.start_as_current_span("checkpoint.runtime.smoke") as span:
                span.set_attribute("sandbox", "subprocess")
                span.set_attribute("timeout_seconds", cfg.timeout)
                traceparent = otel.traceparent_for(span)
                if target.language == "python":
                    from .runtime import py_runner

                    harness = py_runner.run(sample, contract, cfg.timeout, traceparent, otel.exporting())
                else:
                    from .runtime import node_runner

                    harness = node_runner.run(
                        sample, contract, cfg.root, cfg.timeout, traceparent, otel.exporting()
                    )
                span.set_attribute("code.calls", harness.calls)
                if harness.stage in ("import", "call", "harness") and not harness.passed:
                    decide("checkpoint.runtime.smoke", harness.error_type or V.CRASH,
                           harness.message, harness.detail)
                    span.set_status(ot_trace.Status(ot_trace.StatusCode.ERROR, harness.message))

            if result.passed and contract is not None:
                remaining.remove("checkpoint.contract")
                with tracer.start_as_current_span("checkpoint.contract") as span:
                    span.set_attribute("contract.file", target.contract or "")
                    if harness.stage == "contract" and not harness.passed:
                        span.add_event(
                            "schema.violations",
                            {"violations": str(harness.violations), "count": len(harness.violations)},
                        )
                        decide("checkpoint.contract", harness.error_type or V.SCHEMA_MISMATCH,
                               harness.message, {"violations": harness.violations})
                        span.set_status(ot_trace.Status(ot_trace.StatusCode.ERROR, result.message))
            elif result.passed:
                remaining.remove("checkpoint.contract")
                with tracer.start_as_current_span("checkpoint.contract") as span:
                    span.set_attribute("checkpoint.skipped", True)
                    span.set_attribute("reason", "no contract declared")

        # the pipeline shape stays visible even after a short-circuit
        _skip(tracer, parent_ctx, remaining)

        root.set_attribute("checkpoint.verdict", result.verdict)
        if result.error_type:
            root.set_attribute("checkpoint.error_type", result.error_type)
        if not result.passed:
            root.set_status(ot_trace.Status(ot_trace.StatusCode.ERROR, result.message))

    return result
