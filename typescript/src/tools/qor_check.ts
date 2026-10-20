import { z } from "zod";
import type { QorCheck, QorMetricVerdict } from "../core/models.js";

const CHECK_PATH = "/compare/check/inline";
const REQUEST_TIMEOUT_MS = 8_000;
const RETRY_ATTEMPTS = 3;
const RETRY_BACKOFF_MS = 1_000;
/**
 * Worst case for one check: every try times out, with a linear backoff between
 * tries. It must stay well under the 60 s that the MCP SDK gives a client by
 * default, or the caller sees a tool error instead of `unreachable`.
 */
export const MAX_CHECK_MS =
  RETRY_ATTEMPTS * REQUEST_TIMEOUT_MS +
  RETRY_BACKOFF_MS * ((RETRY_ATTEMPTS * (RETRY_ATTEMPTS - 1)) / 2);
const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);

export interface QorCheckRequest {
  platform: string;
  design: string;
  variant: string;
  /** Stage metrics as `read_orfs_metrics` reads them. Non-numbers are dropped. */
  stages: Array<{ metrics: Record<string, unknown> }>;
}

/**
 * Flatten stage metrics into the name -> number map the dashboard takes.
 *
 * ORFS's own `metadata.json` is the merge of the same stage files, so the names
 * match for the metrics those files hold. `metadata.json` adds a few more from
 * other sources (the SDC clock count, some derived timing values), which this
 * server does not send, so the dashboard does not judge them. A later stage wins
 * over an earlier one, and a metric recorded once per sub-run (an array) counts
 * as its last value. The dashboard judges only the metrics it receives, so a
 * single stage gives a verdict for that stage alone.
 */
export function flattenStageMetrics(
  stages: QorCheckRequest["stages"],
): Record<string, number> {
  const flat: Record<string, number> = {};
  for (const { metrics } of stages) {
    for (const [name, raw] of Object.entries(metrics)) {
      // `__iter__N` keys fold into a separate column server-side and match no rule.
      if (name.includes("__iter__")) continue;
      const value = Array.isArray(raw) ? raw[raw.length - 1] : raw;
      if (typeof value === "number" && Number.isFinite(value)) flat[name] = value;
    }
  }
  return flat;
}

const Scalar = z.union([z.string(), z.number()]);
const MetricResponse = z.object({
  metricName: z.string(),
  targetValue: z.number(),
  baseValue: z.number().nullish(),
  deltaPct: z.number().nullish(),
  thresholdPct: z.number().nullish(),
  thresholdValue: z.number().nullish(),
  comparisonType: Scalar.nullish(),
  status: z.string(),
  ruleSource: z.string(),
});
const CheckResponse = z.object({
  status: z.enum(["pass", "fail", "inconclusive", "no_baseline"]),
  baseCommitSha: z.string().nullish(),
  baselineStrategy: z.string().nullish(),
  baseBuildUrl: z.string().nullish(),
  baselinePipeline: z.string().nullish(),
  metrics: z.array(MetricResponse),
  totals: z.object({
    passed: z.number(),
    failed: z.number(),
    missingFromBaseline: z.number(),
  }),
});

function noVerdict(
  status: QorCheck["status"],
  message: string,
  checked: number,
): QorCheck {
  return { status, message, baseline: null, totals: null, failing: [], checked };
}

/**
 * Ask the dashboard to judge one design's metrics against the latest master build.
 *
 * The request carries no commit, no pipeline and no API key. The dashboard reads
 * that as a checkout and answers from public data, so a private platform comes
 * back `inconclusive`. This function never throws: a dashboard that cannot be
 * reached is `unreachable`, which is not a QoR failure.
 */
export async function checkQor(request: QorCheckRequest, baseUrl: string): Promise<QorCheck> {
  const metrics = flattenStageMetrics(request.stages);
  const checked = Object.keys(metrics).length;
  if (checked === 0) {
    return noVerdict("inconclusive", "No numeric metrics to check in the selected stages.", 0);
  }

  const body = JSON.stringify({
    CommitSha: "",
    BranchName: "",
    PipelineId: "",
    PlatformName: request.platform,
    DesignName: request.design,
    VariantName: request.variant,
    Metrics: metrics,
  });

  const url = baseUrl.replace(/\/+$/, "") + CHECK_PATH;
  let lastError = "";
  for (let attempt = 1; attempt <= RETRY_ATTEMPTS; attempt += 1) {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body,
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      if (response.ok) return mapResponse(await response.json(), checked);
      lastError = `HTTP ${response.status}`;
      if (!RETRYABLE_STATUS.has(response.status)) break;
    } catch (e) {
      lastError = (e as Error).message ?? String(e);
    }
    if (attempt < RETRY_ATTEMPTS) {
      await new Promise((resolve) => setTimeout(resolve, RETRY_BACKOFF_MS * attempt));
    }
  }
  return noVerdict("unreachable", `QoR dashboard not reached at ${url}: ${lastError}`, checked);
}

function mapResponse(json: unknown, checked: number): QorCheck {
  const parsed = CheckResponse.safeParse(json);
  if (!parsed.success) {
    return noVerdict("unreachable", "QoR dashboard sent a response in an unknown shape or with an unknown status.", checked);
  }
  const r = parsed.data;

  const failing: QorMetricVerdict[] = r.metrics
    .filter((m) => m.status === "fail")
    .map((m) => ({
      metric: m.metricName,
      value: m.targetValue,
      baseValue: m.baseValue ?? null,
      deltaPct: m.deltaPct ?? null,
      thresholdPct: m.thresholdPct ?? null,
      thresholdValue: m.thresholdValue ?? null,
      comparison: m.comparisonType ?? null,
      ruleSource: m.ruleSource,
    }));

  const baseline =
    r.status === "no_baseline" && r.baseBuildUrl == null
      ? null
      : {
          strategy: r.baselineStrategy ?? null,
          commit: r.baseCommitSha ?? null,
          buildUrl: r.baseBuildUrl ?? null,
          pipeline: r.baselinePipeline ?? null,
        };

  const message =
    r.status === "no_baseline"
      ? "The dashboard has no master build with this platform and design to compare against."
      : r.status === "inconclusive"
        ? "No metric was judged: the platform may be private, or the design has no rules."
        : null;

  return {
    status: r.status,
    message,
    baseline,
    totals: r.totals,
    failing,
    checked,
  };
}
