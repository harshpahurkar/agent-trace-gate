"""Instrumented sandbox harness for Python samples.

Runs as a separate `python -I` process (isolated mode: no PYTHONPATH, no user
site-packages, no script-dir on sys.path). It:

1. joins the parent trace via the TRACEPARENT env var, so its spans nest
   under the parent's `checkpoint.runtime.smoke` span;
2. installs sys.monitoring (PEP 669, 3.12+; sys.setprofile fallback below)
   filtered to the sample's own file, opening a `code.call {qualname}` span
   per function invocation — a hallucinated API call detonates on a visible
   span with the exception recorded at the exact frame;
3. imports the sample module and invokes the contract entrypoint;
4. validates the return value against the contract's pydantic model;
5. prints exactly one machine-readable verdict line to stdout.

Exception -> error_type mapping:
    ModuleNotFoundError            -> hallucinated-import
    ImportError / AttributeError   -> hallucinated-api
    pydantic ValidationError       -> schema-mismatch
    anything else                  -> crash

This file is executed directly (not imported), so it only relies on stdlib
plus the packages installed in the engine's own environment (opentelemetry,
pydantic).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import traceback

MARKER = "AGENTTRACE_VERDICT:"


def emit(stage: str, verdict: str, error_type=None, message="", detail=None, violations=None, calls=0):
    print(
        MARKER
        + json.dumps(
            {
                "stage": stage,
                "verdict": verdict,
                "error_type": error_type,
                "message": message,
                "detail": detail or {},
                "violations": violations or [],
                "calls": calls,
            },
            default=str,
        ),
        flush=True,
    )


def setup_otel():
    """Tracer + parent context from env. Returns (tracer, parent_ctx, provider)."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "agenttrace")})
    )
    if os.environ.get("AGENTTRACE_OTEL", "on") != "off":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").rstrip("/")
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint + "/v1/traces")))
    trace.set_tracer_provider(provider)

    parent_ctx = None
    tp = os.environ.get("TRACEPARENT")
    if tp:
        parent_ctx = TraceContextTextMapPropagator().extract({"traceparent": tp})
    return trace.get_tracer("agenttrace.harness"), parent_ctx, provider


def install_tracing(sample_file: str, tracer, parent_ctx):
    """Per-function-call spans for code defined in the sample file only."""
    from opentelemetry import trace

    stack: list = []
    counter = {"calls": 0}

    def open_span(code):
        parent = stack[-1][1] if stack else parent_ctx
        span = tracer.start_span(f"code.call {code.co_qualname}", context=parent)
        span.set_attribute("code.function", code.co_qualname)
        span.set_attribute("code.filepath", code.co_filename)
        span.set_attribute("code.lineno", code.co_firstlineno)
        stack.append((span, trace.set_span_in_context(span)))
        counter["calls"] += 1

    def close_span(exc=None):
        if not stack:
            return
        span, _ = stack.pop()
        if exc is not None:
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR, f"{type(exc).__name__}: {exc}"))
        span.end()

    if sys.version_info >= (3, 12):
        mon = sys.monitoring
        TOOL = mon.PROFILER_ID
        mon.use_tool_id(TOOL, "agenttrace")
        E = mon.events

        def on_start(code, offset):
            if code.co_filename != sample_file:
                return mon.DISABLE
            open_span(code)

        def on_return(code, offset, retval):
            if code.co_filename != sample_file:
                return mon.DISABLE
            close_span()

        def on_unwind(code, offset, exc):
            # PY_UNWIND must not return DISABLE
            if code.co_filename == sample_file:
                close_span(exc)

        mon.register_callback(TOOL, E.PY_START, on_start)
        mon.register_callback(TOOL, E.PY_RETURN, on_return)
        mon.register_callback(TOOL, E.PY_UNWIND, on_unwind)
        mon.set_events(TOOL, E.PY_START | E.PY_RETURN | E.PY_UNWIND)

        def teardown():
            mon.set_events(TOOL, 0)
            while stack:
                close_span()

    else:  # 3.10 / 3.11 fallback

        def profiler(frame, event, arg):
            if frame.f_code.co_filename != sample_file:
                return
            if event == "call":
                open_span(frame.f_code)
            elif event == "return":
                close_span()

        sys.setprofile(profiler)

        def teardown():
            sys.setprofile(None)
            while stack:
                close_span()

    return counter, teardown


def load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def classify(exc: BaseException) -> tuple[str, dict]:
    if isinstance(exc, ModuleNotFoundError):
        return "hallucinated-import", {"module": exc.name}
    if isinstance(exc, ImportError):
        return "hallucinated-api", {"name": exc.name}
    if isinstance(exc, AttributeError):
        detail = {"name": getattr(exc, "name", None)}
        obj = getattr(exc, "obj", None)
        if obj is not None:
            detail["object"] = getattr(obj, "__name__", type(obj).__name__)
        return "hallucinated-api", detail
    return "crash", {"exception": type(exc).__name__}


def main() -> int:
    sample_path = os.path.abspath(sys.argv[1])
    contract_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None

    tracer, parent_ctx, provider = setup_otel()

    contract = None
    if contract_path:
        try:
            contract = load_module(os.path.abspath(contract_path), "agenttrace_contract")
        except BaseException as exc:  # a broken contract is our problem, not the sample's
            emit("harness", "fail", "harness-error", f"contract failed to load: {exc}")
            return 1

    counter, teardown = install_tracing(sample_path, tracer, parent_ctx)
    calls = 0
    try:
        # stage: import — hallucinated packages detonate here
        try:
            module = load_module(sample_path, "agenttrace_sample")
        except BaseException as exc:
            error_type, detail = classify(exc)
            emit("import", "fail", error_type, f"{type(exc).__name__}: {exc}", detail, calls=counter["calls"])
            return 1

        if contract is None:
            emit("ok", "pass", message="import-only smoke (no contract)", calls=counter["calls"])
            return 0

        # stage: call — hallucinated attributes/methods detonate here
        entry_name = contract.ENTRYPOINT
        entry = getattr(module, entry_name, None)
        if entry is None:
            emit("call", "fail", "hallucinated-api",
                 f"entrypoint '{entry_name}' not defined by sample", {"name": entry_name})
            return 1
        args = copy.deepcopy(getattr(contract, "ARGS", ()))
        kwargs = copy.deepcopy(getattr(contract, "KWARGS", {}))
        try:
            result = entry(*args, **kwargs)
        except BaseException as exc:
            error_type, detail = classify(exc)
            detail["traceback"] = traceback.format_exception(exc)[-3:]
            emit("call", "fail", error_type, f"{type(exc).__name__}: {exc}", detail, calls=counter["calls"])
            return 1
        finally:
            calls = counter["calls"]

        # stage: contract — schema drift detonates here
        returns_model = getattr(contract, "Returns", None)
        if returns_model is not None:
            from pydantic import TypeAdapter, ValidationError

            try:
                TypeAdapter(returns_model).validate_python(result)
            except ValidationError as exc:
                violations = exc.errors(include_url=False)
                for v in violations:
                    v["input"] = repr(v.get("input"))[:120]
                emit("contract", "fail", "schema-mismatch",
                     f"{exc.error_count()} contract violation(s)", violations=violations, calls=calls)
                return 1

        emit("ok", "pass", calls=calls)
        return 0
    finally:
        teardown()
        provider.force_flush(5000)
        provider.shutdown()


if __name__ == "__main__":
    sys.exit(main())
