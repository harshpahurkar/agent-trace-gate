/**
 * OpenTelemetry bootstrap for the Node sandbox.
 *
 * Loaded via `node --import` so the SDK is live before a single line of the
 * untrusted sample evaluates. The OTLP proto exporter reads
 * OTEL_EXPORTER_OTLP_ENDPOINT from the environment (the runner passes it
 * through) and appends /v1/traces per spec.
 */
import { NodeSDK } from "@opentelemetry/sdk-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-proto";

let sdk = null;
if (process.env.AGENTTRACE_OTEL !== "off") {
  sdk = new NodeSDK({
    serviceName: process.env.OTEL_SERVICE_NAME ?? "agenttrace",
    traceExporter: new OTLPTraceExporter(),
  });
  sdk.start();
}

// harness.mjs flushes this on exit
globalThis.__agenttraceSdk = sdk;
