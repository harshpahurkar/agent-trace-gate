/**
 * Instrumented sandbox harness for Node samples.
 *
 * Mirrors the Python harness protocol exactly:
 *  - joins the parent trace via TRACEPARENT (spans nest under
 *    checkpoint.runtime.smoke);
 *  - dynamic-imports the sample — a hallucinated npm package detonates here
 *    as ERR_MODULE_NOT_FOUND;
 *  - wraps the contract entrypoint in a `code.call` span and invokes it — a
 *    hallucinated method detonates as "x.y is not a function" (TypeError);
 *  - zod-validates the return value against the contract schema;
 *  - prints exactly one AGENTTRACE_VERDICT: line to stdout.
 *
 * Classification caveat (documented in docs/limitations.md): JS surfaces a
 * missing method as TypeError, so the harness maps entrypoint TypeErrors to
 * hallucinated-api — a genuine argument-type bug lands in the same bucket.
 */
import { pathToFileURL } from "node:url";
import { context, propagation, trace, SpanStatusCode } from "@opentelemetry/api";

const MARKER = "AGENTTRACE_VERDICT:";
const [, , samplePath, contractPath] = process.argv;

const tracer = trace.getTracer("agenttrace.harness");
let parentCtx = context.active();
if (process.env.TRACEPARENT) {
  parentCtx = propagation.extract(context.active(), { traceparent: process.env.TRACEPARENT });
}

let calls = 0;

function emit(payload) {
  console.log(
    MARKER + JSON.stringify({ detail: {}, violations: [], calls, message: "", ...payload }),
  );
}

function traced(fn, name) {
  return async (...args) => {
    const span = tracer.startSpan(`code.call ${name}`, {}, parentCtx);
    span.setAttribute("code.function", name);
    calls += 1;
    try {
      const result = await context.with(trace.setSpan(parentCtx, span), () => fn(...args));
      span.end();
      return result;
    } catch (err) {
      span.recordException(err);
      span.setStatus({ code: SpanStatusCode.ERROR, message: String(err) });
      span.end();
      throw err;
    }
  };
}

function classifyImportError(err) {
  if (err?.code === "ERR_MODULE_NOT_FOUND" || err?.code === "MODULE_NOT_FOUND") {
    const match = /Cannot find (?:package|module) '([^']+)'/.exec(err.message ?? "");
    return { error_type: "hallucinated-import", detail: { module: match?.[1] ?? null } };
  }
  return { error_type: "crash", detail: { exception: err?.constructor?.name ?? "Error" } };
}

async function main() {
  let contract = null;
  if (contractPath && contractPath !== "-") {
    try {
      contract = await import(pathToFileURL(contractPath).href);
    } catch (err) {
      emit({
        stage: "harness",
        verdict: "fail",
        error_type: "harness-error",
        message: `contract failed to load: ${err.message}`,
      });
      return 1;
    }
  }

  let mod;
  try {
    mod = await import(pathToFileURL(samplePath).href);
  } catch (err) {
    emit({
      stage: "import",
      verdict: "fail",
      message: `${err?.constructor?.name ?? "Error"}: ${err.message}`,
      ...classifyImportError(err),
    });
    return 1;
  }

  if (!contract) {
    emit({ stage: "ok", verdict: "pass", message: "import-only smoke (no contract)" });
    return 0;
  }

  const entryName = contract.entrypoint;
  const entry = mod[entryName];
  if (typeof entry !== "function") {
    emit({
      stage: "call",
      verdict: "fail",
      error_type: "hallucinated-api",
      message: `entrypoint '${entryName}' not exported by sample`,
      detail: { name: entryName },
    });
    return 1;
  }

  let result;
  try {
    result = await traced(entry, entryName)(...(contract.args ?? []));
  } catch (err) {
    emit({
      stage: "call",
      verdict: "fail",
      error_type: err instanceof TypeError ? "hallucinated-api" : "crash",
      message: `${err?.constructor?.name ?? "Error"}: ${err.message}`,
      detail: { exception: err?.constructor?.name ?? "Error" },
    });
    return 1;
  }

  if (contract.schema) {
    const parsed = contract.schema.safeParse(result);
    if (!parsed.success) {
      emit({
        stage: "contract",
        verdict: "fail",
        error_type: "schema-mismatch",
        message: `${parsed.error.issues.length} contract violation(s)`,
        violations: parsed.error.issues,
      });
      return 1;
    }
  }

  emit({ stage: "ok", verdict: "pass" });
  return 0;
}

const code = await main().catch((err) => {
  emit({ stage: "harness", verdict: "fail", error_type: "harness-error", message: String(err) });
  return 1;
});
try {
  await globalThis.__agenttraceSdk?.shutdown();
} catch {
  /* exporter flush failure must not change the verdict */
}
process.exit(code);
