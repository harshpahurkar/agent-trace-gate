"""OpenTelemetry bootstrap for the checkpoint engine.

One tracer provider for the whole CLI run, service name "agenttrace" so the
engine's spans land next to Claude Code's own "claude-code" service in the
same Jaeger UI.

Export policy: if the OTLP endpoint answers a TCP probe we export via
OTLP/HTTP; otherwise spans are still created (the pipeline logic reads them)
but nothing is exported, and the CLI prints a one-line hint instead of
spamming exporter retries.
"""

from __future__ import annotations

import logging
import os
import socket
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import Span, set_span_in_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

SERVICE = "agenttrace"

_configured = False
_exporting = False


def endpoint() -> str:
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").rstrip("/")


def reachable(url: str | None = None, timeout: float = 0.6) -> bool:
    parsed = urlparse(url or endpoint())
    port = parsed.port or (443 if parsed.scheme == "https" else 4318)
    try:
        with socket.create_connection((parsed.hostname or "localhost", port), timeout=timeout):
            return True
    except OSError:
        return False


def configure(mode: str = "auto") -> bool:
    """Set up the global tracer provider. mode: auto | otlp | console | off.

    Returns True when spans are actually being exported somewhere.
    """
    global _configured, _exporting
    if _configured:
        return _exporting

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: SERVICE}))
    if mode == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        _exporting = True
    elif mode == "off":
        _exporting = False
    else:  # auto / otlp
        if mode == "otlp" or reachable():
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint() + "/v1/traces"))
            )
            _exporting = True
        else:
            _exporting = False

    trace.set_tracer_provider(provider)
    # exporter connection errors should never drown the verdict table
    logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)
    _configured = True
    return _exporting


def exporting() -> bool:
    return _exporting


def tracer():
    return trace.get_tracer("agenttrace")


def flush() -> None:
    provider = trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if force_flush:
        force_flush(5000)


def traceparent_for(span: Span) -> str | None:
    """W3C traceparent for `span`, handed to sandbox subprocesses via env."""
    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier, context=set_span_in_context(span))
    return carrier.get("traceparent")


def jaeger_link(trace_id: str) -> str:
    ui = os.environ.get("AGENTTRACE_JAEGER_UI", "http://localhost:16686").rstrip("/")
    return f"{ui}/trace/{trace_id}"
