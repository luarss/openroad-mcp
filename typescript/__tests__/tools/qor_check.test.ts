import { describe, it, expect, vi, afterEach } from "vitest";
import { MAX_CHECK_MS, checkQor, flattenStageMetrics } from "../../src/tools/qor_check.js";

const URL = "https://qor.example/api";
const request = {
  platform: "nangate45",
  design: "gcd",
  variant: "base",
  stages: [{ metrics: { cts__timing__setup__ws: -0.1 } }],
};

function respond(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { status });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("flattenStageMetrics", () => {
  it("keeps numbers, takes the last value of a repeated metric, and lets a later stage win", () => {
    expect(
      flattenStageMetrics([
        { metrics: { a: 1, b: [1, 2, 3], c: "text", d: true, e: Number.NaN } },
        { metrics: { a: 5, "x__iter__2": 9 } },
      ]),
    ).toEqual({ a: 5, b: 3 });
  });
});

describe("checkQor", () => {
  it("makes no request when no stage has a numeric metric", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await checkQor({ ...request, stages: [{ metrics: { name: "x" } }] }, URL);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result).toMatchObject({ status: "inconclusive", checked: 0 });
  });

  it("sends nothing for a platform outside the public list", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await checkQor({ ...request, platform: "gf12" }, URL);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result).toMatchObject({ status: "inconclusive", checked: 0 });
    expect(result.message).toMatch(/gf12.*not on the public list/);
  });

  it("asks for the latest master build: no commit, no pipeline, no key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      respond(200, {
        status: "pass",
        baselineStrategy: "latest-master",
        metrics: [],
        totals: { passed: 3, failed: 0, missingFromBaseline: 0 },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await checkQor(request, `${URL}/`);

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`${URL}/compare/check/inline`);
    expect(init.headers).toEqual({ "Content-Type": "application/json", Accept: "application/json" });
    const sent = JSON.parse(init.body);
    expect(sent).toMatchObject({ CommitSha: "", PipelineId: "", BranchName: "" });
    expect(sent).not.toHaveProperty("JobName");
    expect(sent).not.toHaveProperty("IsLocal");
    expect(result.status).toBe("pass");
    expect(result.failing).toEqual([]);
    expect(result.totals).toEqual({ passed: 3, failed: 0, missingFromBaseline: 0 });
  });

  it("reports only failing metrics and names the baseline", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        respond(200, {
          status: "fail",
          baseCommitSha: "b".repeat(40),
          baselineStrategy: "latest-master",
          baseBuildUrl: "https://qor.example/builds/9",
          metrics: [
            { metricName: "ok", targetValue: 1, status: "pass", ruleSource: "rule_config" },
            { metricName: "bad", targetValue: 2, baseValue: 1, status: "fail", ruleSource: "rule_config" },
          ],
          totals: { passed: 1, failed: 1, missingFromBaseline: 0 },
        }),
      ),
    );

    const result = await checkQor(request, URL);

    expect(result.failing.map((m) => m.metric)).toEqual(["bad"]);
    expect(result.baseline).toEqual({
      strategy: "latest-master",
      commit: "b".repeat(40),
      buildUrl: "https://qor.example/builds/9",
      pipeline: null,
    });
  });

  it("says so when no master build exists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        respond(200, {
          status: "no_baseline",
          baselineStrategy: "none",
          metrics: [],
          totals: { passed: 0, failed: 0, missingFromBaseline: 0 },
        }),
      ),
    );

    const result = await checkQor(request, URL);

    expect(result.status).toBe("no_baseline");
    expect(result.baseline).toBeNull();
    expect(result.message).toMatch(/no master build/);
  });

  it("does not retry a client error, and reports it as unreachable", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(400));
    vi.stubGlobal("fetch", fetchMock);

    const result = await checkQor(request, URL);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.status).toBe("unreachable");
    expect(result.message).toContain("HTTP 400");
  });

  it("retries a transient status, then succeeds", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(503))
      .mockResolvedValueOnce(
        respond(200, { status: "pass", metrics: [], totals: { passed: 1, failed: 0, missingFromBaseline: 0 } }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const pending = checkQor(request, URL);
    await vi.runAllTimersAsync();

    expect((await pending).status).toBe("pass");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gives up after three network failures without throwing", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockRejectedValue(new Error("connect ECONNREFUSED"));
    vi.stubGlobal("fetch", fetchMock);

    const pending = checkQor(request, URL);
    await vi.runAllTimersAsync();
    const result = await pending;

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(result.status).toBe("unreachable");
    expect(result.message).toContain("ECONNREFUSED");
  });

  it("stays under the default MCP client timeout of 60 s", () => {
    expect(MAX_CHECK_MS).toBeLessThan(40_000);
  });

  it("rejects a status it does not know", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        respond(200, { status: "maybe", metrics: [], totals: { passed: 0, failed: 0, missingFromBaseline: 0 } }),
      ),
    );

    const result = await checkQor(request, URL);

    expect(result.status).toBe("unreachable");
    expect(result.message).toMatch(/unknown status/);
  });

  it("rejects a response in an unknown shape", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(200, { hello: "world" })));

    const result = await checkQor(request, URL);

    expect(result.status).toBe("unreachable");
    expect(result.message).toMatch(/unknown shape/);
  });
});
