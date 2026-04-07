"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type {
  PresetName,
  RunOverrides,
  RunRecord,
  RunStepName,
  StepStatus,
} from "@/lib/types";

const STEP_ORDER: RunStepName[] = ["seed", "enrich", "score", "rank"];

const PRESET_COPY: Record<PresetName, { title: string; subtitle: string }> = {
  short: {
    title: "Short",
    subtitle: "Smoke-test run with very small limits.",
  },
  standard: {
    title: "Standard",
    subtitle: "Balanced run for day-to-day usage.",
  },
  deep: {
    title: "Deep",
    subtitle: "Large run for fuller research coverage.",
  },
};

const OVERRIDE_FIELDS = {
  seed: [
    { key: "delaySeconds", label: "Delay Seconds", type: "number" },
    { key: "manualCount", label: "Manual Count", type: "number" },
    { key: "aggregatorCount", label: "Aggregator Count", type: "number" },
    { key: "hashtagLimitPerTag", label: "Hashtag Limit / Tag", type: "number" },
    { key: "waitSeconds", label: "Wait Seconds", type: "number" },
    { key: "skipApify", label: "Skip Apify", type: "boolean" },
    { key: "overwrite", label: "Overwrite Files", type: "boolean" },
  ],
  enrich: [
    { key: "batchSize", label: "Batch Size", type: "number" },
    { key: "delaySeconds", label: "Delay Seconds", type: "number" },
    { key: "waitSeconds", label: "Wait Seconds", type: "number" },
    { key: "minFollowersForPosts", label: "Min Followers For Posts", type: "number" },
    { key: "maxPostAccounts", label: "Max Post Accounts", type: "number" },
    { key: "maxCommentAccounts", label: "Max Comment Accounts", type: "number" },
    { key: "postsPerAccount", label: "Posts Per Account", type: "number" },
    { key: "commentsPerAccount", label: "Comments Per Account", type: "number" },
    { key: "commentsPerPost", label: "Comments Per Post", type: "number" },
  ],
  score: [
    { key: "model", label: "LLM Model", type: "text" },
    { key: "maxCaptions", label: "Max Captions", type: "number" },
    { key: "maxComments", label: "Max Comments", type: "number" },
    { key: "minCaptions", label: "Min Captions", type: "number" },
    { key: "minComments", label: "Min Comments", type: "number" },
  ],
  rank: [
    { key: "minFollowers", label: "Min Followers", type: "number" },
    { key: "maxAccounts", label: "Max Accounts", type: "number" },
    { key: "topPerTier", label: "Top Per Tier", type: "number" },
  ],
} as const;

interface DashboardResponse {
  activeRunId: string | null;
  queuedRunIds: string[];
  runs: RunRecord[];
}

interface RunDetailResponse {
  run: RunRecord;
  logs: string[];
}

function classForStatus(status?: string): string {
  switch (status) {
    case "succeeded":
      return "bg-emerald-100 text-emerald-700";
    case "running":
      return "bg-sky-100 text-sky-700";
    case "failed":
      return "bg-rose-100 text-rose-700";
    case "queued":
      return "bg-amber-100 text-amber-700";
    case "cancelled":
      return "bg-slate-200 text-slate-600";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

function sanitizeOverrides(input: RunOverrides): RunOverrides | undefined {
  const output: RunOverrides = {};

  for (const step of Object.keys(input) as Array<keyof RunOverrides>) {
    const stepValues = input[step] as Record<string, unknown> | undefined;
    if (!stepValues) {
      continue;
    }

    const cleanedEntries = Object.entries(stepValues).filter(([, value]) => {
      if (value === undefined || value === null || value === "") {
        return false;
      }
      if (typeof value === "number") {
        return Number.isFinite(value);
      }
      return true;
    });

    if (cleanedEntries.length > 0) {
      output[step] = Object.fromEntries(cleanedEntries) as never;
    }
  }

  return Object.keys(output).length > 0 ? output : undefined;
}

export default function RunPage() {
  const [preset, setPreset] = useState<PresetName>("short");
  const [overrides, setOverrides] = useState<RunOverrides>({});
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [queuedRunIds, setQueuedRunIds] = useState<string[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<RunRecord | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const logPanelRef = useRef<HTMLDivElement | null>(null);

  const refreshDashboard = async () => {
    const response = await fetch("/api/runs", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Failed to load runs dashboard.");
    }
    const payload = (await response.json()) as DashboardResponse;
    setRuns(payload.runs);
    setActiveRunId(payload.activeRunId);
    setQueuedRunIds(payload.queuedRunIds);
    return payload;
  };

  const refreshRun = async (runId: string) => {
    const response = await fetch(`/api/runs/${runId}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Failed to load run details.");
    }
    const payload = (await response.json()) as RunDetailResponse;
    setSelectedRun(payload.run);
    setLogs(payload.logs);
  };

  useEffect(() => {
    let mounted = true;

    (async () => {
      try {
        const payload = await refreshDashboard();
        if (!mounted) {
          return;
        }
        if (!selectedRunId && payload.runs.length > 0) {
          setSelectedRunId(payload.activeRunId || payload.runs[0].id);
        }
      } catch (error) {
        if (mounted) {
          setErrorMessage((error as Error).message);
        }
      }
    })();

    const timer = setInterval(() => {
      refreshDashboard().catch((error) => {
        setErrorMessage((error as Error).message);
      });
    }, 7000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }

    refreshRun(selectedRunId).catch((error) => {
      setErrorMessage((error as Error).message);
    });
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }

    eventSourceRef.current?.close();

    const source = new EventSource(`/api/runs/${selectedRunId}/stream`);
    eventSourceRef.current = source;

    const updateFromEvent = () => {
      refreshDashboard().catch(() => undefined);
      refreshRun(selectedRunId).catch(() => undefined);
    };

    const handleSnapshot = (event: MessageEvent) => {
      const payload = JSON.parse(event.data) as { run: RunRecord; logs: string[] };
      setSelectedRun(payload.run);
      setLogs(payload.logs || []);
    };

    const handleLog = (event: MessageEvent) => {
      const payload = JSON.parse(event.data) as { text: string; stream: string; step: string };
      setLogs((previous) => {
        const next = [...previous, `[${payload.step}] ${payload.text}`];
        return next.slice(-600);
      });
    };

    source.addEventListener("snapshot", handleSnapshot);
    source.addEventListener("log", handleLog);
    source.addEventListener("step_started", updateFromEvent);
    source.addEventListener("step_finished", updateFromEvent);
    source.addEventListener("run_started", updateFromEvent);
    source.addEventListener("run_finished", updateFromEvent);
    source.addEventListener("run_failed", updateFromEvent);
    source.addEventListener("run_cancelled", updateFromEvent);

    source.onerror = () => {
      source.close();
      eventSourceRef.current = null;
    };

    return () => {
      source.close();
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null;
      }
    };
  }, [selectedRunId]);

  useEffect(() => {
    if (!logPanelRef.current) {
      return;
    }
    logPanelRef.current.scrollTop = logPanelRef.current.scrollHeight;
  }, [logs]);

  const selectedStepMap = useMemo(() => {
    const map = new Map<string, StepStatus>();
    for (const step of selectedRun?.steps || []) {
      map.set(step.name, step.status);
    }
    return map;
  }, [selectedRun]);

  const handleOverrideChange = (
    step: keyof RunOverrides,
    key: string,
    type: "number" | "text" | "boolean",
    value: string | boolean
  ) => {
    setOverrides((previous) => {
      const next = { ...previous };
      const stepValues = { ...((next[step] as Record<string, unknown>) || {}) };

      if (type === "boolean") {
        stepValues[key] = value;
      } else if (type === "number") {
        stepValues[key] = value === "" ? undefined : Number(value);
      } else {
        stepValues[key] = value;
      }

      next[step] = stepValues as never;
      return next;
    });
  };

  const startRun = async () => {
    setBusy(true);
    setErrorMessage(null);

    try {
      const payload = {
        preset,
        overrides: sanitizeOverrides(overrides),
      };

      const response = await fetch("/api/runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorPayload = (await response.json()) as { error?: string };
        throw new Error(errorPayload.error || "Could not start run.");
      }

      const body = (await response.json()) as { run: RunRecord };
      setSelectedRunId(body.run.id);
      setSelectedRun(body.run);
      setLogs([]);
      await refreshDashboard();
    } catch (error) {
      setErrorMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const cancelSelectedRun = async () => {
    if (!selectedRunId) {
      return;
    }

    setBusy(true);
    try {
      const response = await fetch(`/api/runs/${selectedRunId}/cancel`, {
        method: "POST",
      });
      if (!response.ok) {
        const payload = (await response.json()) as { error?: string };
        throw new Error(payload.error || "Failed to cancel run.");
      }
      await refreshDashboard();
      await refreshRun(selectedRunId);
    } catch (error) {
      setErrorMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-8">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-slate-500">
              Queue Status
            </p>
            <h1 className="mt-1 text-xl font-semibold text-slate-900">
              Pipeline Operator Console
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className={`rounded-full px-3 py-1 ${classForStatus(activeRunId ? "running" : "succeeded")}`}>
              {activeRunId ? `Active Run: ${activeRunId.slice(0, 8)}` : "No Active Run"}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
              Queued: {queuedRunIds.length}
            </span>
          </div>
        </div>
      </section>

      {errorMessage ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {errorMessage}
        </section>
      ) : null}

      <section className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Start New Run</h2>
            <button
              type="button"
              onClick={() => setAdvancedOpen((previous) => !previous)}
              className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
            >
              {advancedOpen ? "Hide Advanced" : "Show Advanced"}
            </button>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {(Object.keys(PRESET_COPY) as PresetName[]).map((name) => (
              <button
                type="button"
                key={name}
                onClick={() => setPreset(name)}
                className={`rounded-xl border p-4 text-left transition ${
                  preset === name
                    ? "border-sky-300 bg-sky-50"
                    : "border-slate-200 hover:bg-slate-50"
                }`}
              >
                <p className="text-sm font-semibold text-slate-900">{PRESET_COPY[name].title}</p>
                <p className="mt-1 text-xs text-slate-600">{PRESET_COPY[name].subtitle}</p>
              </button>
            ))}
          </div>

          {advancedOpen ? (
            <div className="mt-5 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
              {(Object.keys(OVERRIDE_FIELDS) as Array<keyof typeof OVERRIDE_FIELDS>).map((stepName) => (
                <div key={stepName}>
                  <h3 className="text-sm font-semibold capitalize text-slate-800">{stepName}</h3>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    {OVERRIDE_FIELDS[stepName].map((field) => {
                      const rawValue = (overrides[stepName as keyof RunOverrides] as Record<string, unknown> | undefined)?.[field.key];

                      if (field.type === "boolean") {
                        return (
                          <label
                            key={`${stepName}-${field.key}`}
                            className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
                          >
                            <span>{field.label}</span>
                            <input
                              type="checkbox"
                              checked={Boolean(rawValue)}
                              onChange={(event) =>
                                handleOverrideChange(stepName as keyof RunOverrides, field.key, "boolean", event.target.checked)
                              }
                            />
                          </label>
                        );
                      }

                      return (
                        <label key={`${stepName}-${field.key}`} className="flex flex-col gap-1 text-xs text-slate-600">
                          {field.label}
                          <input
                            type={field.type === "number" ? "number" : "text"}
                            value={rawValue === undefined ? "" : String(rawValue)}
                            onChange={(event) =>
                              handleOverrideChange(
                                stepName as keyof RunOverrides,
                                field.key,
                                field.type,
                                event.target.value
                              )
                            }
                            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                          />
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={startRun}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {busy ? "Starting..." : "Start Run"}
            </button>
            {selectedRun && (selectedRun.status === "running" || selectedRun.status === "queued") ? (
              <button
                type="button"
                disabled={busy}
                onClick={cancelSelectedRun}
                className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed"
              >
                Cancel Selected Run
              </button>
            ) : null}
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Recent Runs</h2>
          <div className="mt-4 max-h-[420px] space-y-2 overflow-auto pr-1">
            {runs.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-200 p-3 text-sm text-slate-500">
                No runs yet.
              </p>
            ) : (
              runs.map((run) => (
                <button
                  type="button"
                  key={run.id}
                  onClick={() => setSelectedRunId(run.id)}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                    selectedRunId === run.id
                      ? "border-sky-300 bg-sky-50"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-slate-900">{run.id.slice(0, 8)}</p>
                    <span className={`rounded-full px-2 py-0.5 text-xs ${classForStatus(run.status)}`}>
                      {run.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {run.preset} · {new Date(run.createdAt).toLocaleString()}
                  </p>
                </button>
              ))
            )}
          </div>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Step Progress</h2>
          <div className="mt-4 space-y-3">
            {STEP_ORDER.map((stepName, index) => {
              const stepStatus = selectedStepMap.get(stepName) || "pending";
              return (
                <div key={stepName} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600">
                      {index + 1}
                    </span>
                    <p className="text-sm font-semibold capitalize text-slate-800">{stepName}</p>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${classForStatus(stepStatus)}`}>
                    {stepStatus}
                  </span>
                </div>
              );
            })}
          </div>

          {selectedRun ? (
            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
              <p className="font-semibold text-slate-900">Run Summary</p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-600">
                <p>Raw handles: {selectedRun.summary.rawHandleCount}</p>
                <p>Scored: {selectedRun.summary.scoredCount}</p>
                <p>Final ranked: {selectedRun.summary.finalRankedCount}</p>
                <p>Review bucket: {selectedRun.summary.reviewBucketCount}</p>
              </div>
              {selectedRun.errorMessage ? (
                <p className="mt-3 rounded bg-rose-100 px-2 py-1 text-rose-700">
                  {selectedRun.errorMessage}
                </p>
              ) : null}
            </div>
          ) : null}
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Live Log Stream</h2>
          <div
            ref={logPanelRef}
            className="mt-4 h-[380px] overflow-auto rounded-xl bg-slate-950 p-3 font-mono text-xs text-slate-200"
          >
            {logs.length === 0 ? (
              <p className="text-slate-400">Waiting for logs...</p>
            ) : (
              logs.map((line, index) => (
                <p key={`${index}-${line.slice(0, 12)}`} className="whitespace-pre-wrap">
                  {line}
                </p>
              ))
            )}
          </div>
        </article>
      </section>
    </main>
  );
}
