"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type MonitorJobStatus = "running" | "succeeded" | "failed";
type MonitorJobKind = "bootstrap" | "run" | "schedule" | "generate";

interface MonitorJob {
  id: string;
  kind: MonitorJobKind;
  status: MonitorJobStatus;
  command: string;
  startedAt: string;
  finishedAt?: string;
  exitCode?: number;
  logs: string[];
  errorMessage?: string;
}

interface MonitorOverview {
  trackedCount: number;
  seenPostsCount: number;
  queueCount: number;
  pendingQueueCount: number;
  runsCount: number;
  recentQueue: Array<{
    id: number;
    username: string;
    postId: string;
    caption: string;
    url: string;
    postedAt: string;
    detectedAt: string;
    status: string;
    isVideo: number;
    mediaType: string;
  }>;
  recentSeenPosts: Array<{
    username: string;
    postId: string;
    url: string;
    postedAt: string;
    firstSeenAt: string;
    caption: string;
  }>;
  recentRuns: Array<{
    runId: string;
    mode: string;
    startedAt: string;
    endedAt: string;
    accountsChecked: number;
    newPostsFound: number;
    failedAccounts: number;
    status: string;
    errorSummary: string;
  }>;
  trackedAccounts: Array<{
    username: string;
    tier: string;
    finalScore: number | null;
    active: number;
    updatedAt: string;
  }>;
  activeJob: MonitorJob | null;
  recentJobs: MonitorJob[];
}

function classForStatus(status?: string): string {
  switch (status) {
    case "succeeded":
      return "bg-emerald-100 text-emerald-700";
    case "running":
      return "bg-sky-100 text-sky-700";
    case "failed":
      return "bg-rose-100 text-rose-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

async function postJson<T>(url: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const body = (await response.json()) as T & { error?: string };
  if (!response.ok) {
    throw new Error(body.error || "Request failed.");
  }
  return body;
}

export default function MonitorPage() {
  const [overview, setOverview] = useState<MonitorOverview | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const [bootstrapLimit, setBootstrapLimit] = useState(20);
  const [bootstrapSourceRunId, setBootstrapSourceRunId] = useState("");

  const [runMode, setRunMode] = useState<"live" | "mock">("live");
  const [runBatchSize, setRunBatchSize] = useState(25);
  const [runPostsPerAccount, setRunPostsPerAccount] = useState(5);
  const [runLimitAccounts, setRunLimitAccounts] = useState(20);
  const [runDelaySeconds, setRunDelaySeconds] = useState(2.5);
  const [runMaxRetries, setRunMaxRetries] = useState(2);
  const [runAutoGenerateComments, setRunAutoGenerateComments] = useState(true);
  const [runGenerateLimit, setRunGenerateLimit] = useState(10);
  const [runWhisperModel, setRunWhisperModel] = useState("base.en");
  const [runFixture, setRunFixture] = useState("data/monitor/mock_posts.json");
  const [runMockFailUsernames, setRunMockFailUsernames] = useState("");

  const [scheduleName, setScheduleName] = useState("toms-part2-monitor-4h");
  const [scheduleCron, setScheduleCron] = useState("0 */4 * * *");
  const [scheduleTimezone, setScheduleTimezone] = useState("America/Phoenix");
  const [scheduleDisable, setScheduleDisable] = useState(false);
  const [scheduleActorTaskId, setScheduleActorTaskId] = useState("");
  const [scheduleActorId, setScheduleActorId] = useState("");
  const [scheduleRunInput, setScheduleRunInput] = useState(
    '{"mode":"live","posts_per_account":5,"batch_size":25}'
  );

  const refreshOverview = useCallback(async () => {
    const response = await fetch("/api/monitor", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Failed to load monitor overview.");
    }
    const payload = (await response.json()) as MonitorOverview;
    setOverview(payload);
    return payload;
  }, []);

  useEffect(() => {
    let mounted = true;
    refreshOverview().catch((error) => {
      if (mounted) {
        setErrorMessage((error as Error).message);
      }
    });

    const timer = setInterval(() => {
      refreshOverview().catch((error) => {
        if (mounted) {
          setErrorMessage((error as Error).message);
        }
      });
    }, 6000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [refreshOverview]);

  const recentJobs = useMemo(() => {
    const jobs = overview?.recentJobs || [];
    const active = overview?.activeJob;
    if (!active) {
      return jobs;
    }
    return [active, ...jobs.filter((job) => job.id !== active.id)];
  }, [overview]);

  const executeAction = async (
    actionName: string,
    endpoint: string,
    payload: Record<string, unknown>,
    successText?: string
  ) => {
    setBusyAction(actionName);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      await postJson<{ job: MonitorJob }>(endpoint, payload);
      await refreshOverview();
      if (successText) {
        setSuccessMessage(successText);
      }
    } catch (error) {
      setErrorMessage((error as Error).message);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-8">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-slate-500">
              Part 2 Monitor
            </p>
            <h1 className="mt-1 text-xl font-semibold text-slate-900">
              Ongoing Post Detection Console
            </h1>
          </div>
          <button
            type="button"
            onClick={() => refreshOverview().catch((error) => setErrorMessage((error as Error).message))}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Refresh
          </button>
        </div>
        {errorMessage ? (
          <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {errorMessage}
          </p>
        ) : null}
        {successMessage ? (
          <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {successMessage}
          </p>
        ) : null}
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[
          ["Tracked", String(overview?.trackedCount || 0)],
          ["Seen Posts", String(overview?.seenPostsCount || 0)],
          ["Queue Total", String(overview?.queueCount || 0)],
          ["Queue Pending", String(overview?.pendingQueueCount || 0)],
          ["Monitor Runs", String(overview?.runsCount || 0)],
        ].map(([label, value]) => (
          <article key={label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
          </article>
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">1) Bootstrap Watchlist</h2>
          <p className="mt-1 text-xs text-slate-500">
            Upsert tracked accounts from default `data/final_ranked.csv` or from latest successful Run.
          </p>
          <div className="mt-4 space-y-3">
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Limit Accounts
              <input
                type="number"
                min={1}
                max={500}
                value={bootstrapLimit}
                onChange={(event) => setBootstrapLimit(Number(event.target.value))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Source Run ID (optional)
              <input
                value={bootstrapSourceRunId}
                onChange={(event) => setBootstrapSourceRunId(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                placeholder="optional trace id"
              />
            </label>
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() =>
                executeAction("bootstrap", "/api/monitor/bootstrap", {
                  limit: bootstrapLimit,
                  sourceRunId: bootstrapSourceRunId || undefined,
                }, "Tracked accounts bootstrapped from default final_ranked.csv.")
              }
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {busyAction === "bootstrap" ? "Bootstrapping..." : "Bootstrap"}
            </button>
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() =>
                executeAction(
                  "bootstrap-latest-run",
                  "/api/monitor/bootstrap",
                  {
                    limit: bootstrapLimit,
                    useLatestSuccessfulRun: true,
                  },
                  "Tracked accounts bootstrapped from latest successful Run."
                )
              }
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-slate-200"
            >
              {busyAction === "bootstrap-latest-run"
                ? "Bootstrapping..."
                : "Bootstrap From Latest Run"}
            </button>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">2) Run Monitor Job</h2>
          <p className="mt-1 text-xs text-slate-500">
            Poll latest posts/account, dedupe in seen registry, and queue only reel/video posts for Engage.
          </p>
          <div className="mt-4 grid gap-3">
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Mode
              <select
                value={runMode}
                onChange={(event) => setRunMode(event.target.value as "live" | "mock")}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              >
                <option value="live">Live</option>
                <option value="mock">Mock</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Batch Size
              <input
                type="number"
                min={1}
                max={50}
                value={runBatchSize}
                onChange={(event) => setRunBatchSize(Number(event.target.value))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Posts Per Account
              <input
                type="number"
                min={1}
                max={10}
                value={runPostsPerAccount}
                onChange={(event) => setRunPostsPerAccount(Number(event.target.value))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Limit Accounts (0 = all active)
              <input
                type="number"
                min={0}
                max={5000}
                value={runLimitAccounts}
                onChange={(event) => setRunLimitAccounts(Number(event.target.value))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Delay Seconds
              <input
                type="number"
                step="0.1"
                min={0}
                max={30}
                value={runDelaySeconds}
                onChange={(event) => setRunDelaySeconds(Number(event.target.value))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Max Retries
              <input
                type="number"
                min={0}
                max={5}
                value={runMaxRetries}
                onChange={(event) => setRunMaxRetries(Number(event.target.value))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Generate Limit (Top N Reels)
              <input
                type="number"
                min={1}
                max={100}
                value={runGenerateLimit}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  setRunGenerateLimit(Number.isFinite(value) ? Math.max(1, Math.min(100, value)) : 10);
                }}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Whisper Model
              <input
                value={runWhisperModel}
                onChange={(event) => setRunWhisperModel(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                placeholder="base.en"
              />
            </label>
            <label className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              Auto Generate Comments After Run
              <input
                type="checkbox"
                checked={runAutoGenerateComments}
                onChange={(event) => setRunAutoGenerateComments(event.target.checked)}
              />
            </label>
            {runMode === "mock" ? (
              <>
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Mock Fixture Path
                  <input
                    value={runFixture}
                    onChange={(event) => setRunFixture(event.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Mock Fail Usernames (comma-separated)
                  <input
                    value={runMockFailUsernames}
                    onChange={(event) => setRunMockFailUsernames(event.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                    placeholder="simulate partial failure"
                  />
                </label>
              </>
            ) : null}
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() =>
                executeAction("run", "/api/monitor/run", {
                  mode: runMode,
                  batchSize: runBatchSize,
                  postsPerAccount: runPostsPerAccount,
                  limitAccounts: runLimitAccounts,
                  delaySeconds: runDelaySeconds,
                  maxRetries: runMaxRetries,
                  autoGenerateComments: runAutoGenerateComments,
                  generateLimit: runGenerateLimit,
                  whisperModel: runWhisperModel || "base.en",
                  fixture: runMode === "mock" ? runFixture : undefined,
                  mockFailUsernames:
                    runMode === "mock" ? runMockFailUsernames || undefined : undefined,
                }, "Monitor run completed. Reels/videos were queued for Engage.")
              }
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {busyAction === "run" ? "Running..." : "Run Monitor"}
            </button>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">3) Ensure 4-Hour Schedule</h2>
          <p className="mt-1 text-xs text-slate-500">
            Optional for production. For assessment demo, keep this disabled and run monitor manually.
          </p>
          <div className="mt-4 grid gap-3">
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Schedule Name
              <input
                value={scheduleName}
                onChange={(event) => setScheduleName(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Cron
              <input
                value={scheduleCron}
                onChange={(event) => setScheduleCron(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Timezone
              <input
                value={scheduleTimezone}
                onChange={(event) => setScheduleTimezone(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Actor Task ID (preferred, optional if env set)
              <input
                value={scheduleActorTaskId}
                onChange={(event) => setScheduleActorTaskId(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Actor ID (fallback)
              <input
                value={scheduleActorId}
                onChange={(event) => setScheduleActorId(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Run Input JSON
              <textarea
                rows={3}
                value={scheduleRunInput}
                onChange={(event) => setScheduleRunInput(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
            <label className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              Disable Schedule
              <input
                type="checkbox"
                checked={scheduleDisable}
                onChange={(event) => setScheduleDisable(event.target.checked)}
              />
            </label>
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() =>
                executeAction("schedule", "/api/monitor/schedule", {
                  name: scheduleName,
                  cron: scheduleCron,
                  timezone: scheduleTimezone,
                  disable: scheduleDisable,
                  actorTaskId: scheduleActorTaskId || undefined,
                  actorId: scheduleActorId || undefined,
                  runInput: scheduleRunInput || undefined,
                }, "Schedule ensure call completed (check logs below).")
              }
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {busyAction === "schedule" ? "Updating..." : "Ensure Schedule"}
            </button>
          </div>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Recent Detected Posts Queue</h2>
          <p className="mt-1 text-xs text-slate-500">
            `new_posts_queue` ordered by detection time.
          </p>
          <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Username</th>
                  <th className="px-3 py-2">Post ID</th>
                  <th className="px-3 py-2">URL</th>
                  <th className="px-3 py-2">Media</th>
                  <th className="px-3 py-2">Posted</th>
                  <th className="px-3 py-2">Detected</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {(overview?.recentQueue || []).length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-4 text-slate-500">
                      No queued posts yet.
                    </td>
                  </tr>
                ) : (
                  (overview?.recentQueue || []).map((row) => (
                    <tr key={row.id} className="border-t border-slate-200">
                      <td className="px-3 py-2 font-semibold text-slate-900">{row.username}</td>
                      <td className="px-3 py-2">{row.postId}</td>
                      <td className="px-3 py-2">
                        {row.url ? (
                          <a
                            href={row.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-sky-700 hover:underline"
                          >
                            Open Post
                          </a>
                        ) : (
                          <span className="text-slate-400">N/A</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {row.isVideo ? "video" : "non-video"} · {row.mediaType || "unknown"}
                      </td>
                      <td className="px-3 py-2">
                        {row.postedAt ? new Date(row.postedAt).toLocaleString() : "-"}
                      </td>
                      <td className="px-3 py-2">
                        {row.detectedAt ? new Date(row.detectedAt).toLocaleString() : "-"}
                      </td>
                      <td className="px-3 py-2">{row.status}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Monitor Job Logs</h2>
          <div className="mt-3 max-h-[420px] space-y-2 overflow-auto rounded-xl border border-slate-200 bg-slate-950 p-3 text-xs text-slate-200">
            {recentJobs.length === 0 ? (
              <p className="text-slate-400">No monitor jobs started from UI yet.</p>
            ) : (
              recentJobs.map((job) => (
                <div key={job.id} className="rounded-lg border border-slate-700 bg-slate-900 p-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold text-slate-100">
                      {job.kind} · {job.id.slice(0, 8)}
                    </p>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${classForStatus(job.status)}`}>
                      {job.status}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400">{job.command}</p>
                  <div className="mt-2 space-y-1">
                    {job.logs.length === 0 ? (
                      <p className="text-slate-500">No logs.</p>
                    ) : (
                      job.logs.slice(-12).map((line, index) => (
                        <p key={`${job.id}-${index}-${line.slice(0, 12)}`} className="whitespace-pre-wrap text-slate-300">
                          {line}
                        </p>
                      ))
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </article>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">Recently Scraped Posts (Seen Registry)</h2>
        <p className="mt-1 text-xs text-slate-500">
          Most recently seen posts, including ones already processed earlier.
        </p>
        <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Username</th>
                <th className="px-3 py-2">Post ID</th>
                <th className="px-3 py-2">URL</th>
                <th className="px-3 py-2">Posted At</th>
                <th className="px-3 py-2">First Seen</th>
              </tr>
            </thead>
            <tbody>
              {(overview?.recentSeenPosts || []).length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-slate-500">
                    No seen posts yet.
                  </td>
                </tr>
              ) : (
                (overview?.recentSeenPosts || []).map((row) => (
                  <tr key={`${row.username}-${row.postId}`} className="border-t border-slate-200">
                    <td className="px-3 py-2 font-semibold text-slate-900">{row.username}</td>
                    <td className="px-3 py-2">{row.postId}</td>
                    <td className="px-3 py-2">
                      {row.url ? (
                        <a
                          href={row.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-sky-700 hover:underline"
                        >
                          Open Post
                        </a>
                      ) : (
                        <span className="text-slate-400">N/A</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {row.postedAt ? new Date(row.postedAt).toLocaleString() : "-"}
                    </td>
                    <td className="px-3 py-2">
                      {row.firstSeenAt ? new Date(row.firstSeenAt).toLocaleString() : "-"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Monitor Runs</h2>
          <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Run</th>
                  <th className="px-3 py-2">Mode</th>
                  <th className="px-3 py-2">Checked</th>
                  <th className="px-3 py-2">New</th>
                  <th className="px-3 py-2">Failed</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {(overview?.recentRuns || []).length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-4 text-slate-500">
                      No monitor runs recorded yet.
                    </td>
                  </tr>
                ) : (
                  (overview?.recentRuns || []).map((run) => (
                    <tr key={run.runId} className="border-t border-slate-200">
                      <td className="px-3 py-2 font-semibold text-slate-900">{run.runId.slice(0, 8)}</td>
                      <td className="px-3 py-2">{run.mode}</td>
                      <td className="px-3 py-2">{run.accountsChecked}</td>
                      <td className="px-3 py-2">{run.newPostsFound}</td>
                      <td className="px-3 py-2">{run.failedAccounts}</td>
                      <td className="px-3 py-2">
                        <span className={`rounded-full px-2 py-0.5 text-xs ${classForStatus(run.status)}`}>
                          {run.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Tracked Accounts</h2>
          <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Username</th>
                  <th className="px-3 py-2">Tier</th>
                  <th className="px-3 py-2">Score</th>
                  <th className="px-3 py-2">Active</th>
                </tr>
              </thead>
              <tbody>
                {(overview?.trackedAccounts || []).length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-4 text-slate-500">
                      No tracked accounts yet. Run bootstrap first.
                    </td>
                  </tr>
                ) : (
                  (overview?.trackedAccounts || []).map((account) => (
                    <tr key={account.username} className="border-t border-slate-200">
                      <td className="px-3 py-2 font-semibold text-slate-900">{account.username}</td>
                      <td className="px-3 py-2">{account.tier || "-"}</td>
                      <td className="px-3 py-2">
                        {account.finalScore === null ? "-" : account.finalScore.toFixed(4)}
                      </td>
                      <td className="px-3 py-2">{account.active ? "yes" : "no"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </main>
  );
}
