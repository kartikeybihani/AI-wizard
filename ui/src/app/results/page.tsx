"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { CsvTableResult, RunRecord } from "@/lib/types";

interface DashboardResponse {
  activeRunId: string | null;
  queuedRunIds: string[];
  runs: RunRecord[];
}

interface ResultsResponse {
  run: RunRecord;
  finalRanked: CsvTableResult;
  reviewBucket: CsvTableResult;
}

function parseMaybeNumber(value: string): number | null {
  if (value === "") {
    return null;
  }
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function compareValues(a: string, b: string, direction: "asc" | "desc") {
  const aNum = parseMaybeNumber(a);
  const bNum = parseMaybeNumber(b);

  if (aNum !== null && bNum !== null) {
    return direction === "asc" ? aNum - bNum : bNum - aNum;
  }

  return direction === "asc" ? a.localeCompare(b) : b.localeCompare(a);
}

function formatFollowers(value: string): string {
  const count = parseMaybeNumber(value);
  if (count === null) {
    return value;
  }

  if (count >= 1_000_000) {
    const inMillions = count / 1_000_000;
    const decimals = inMillions >= 10 ? 1 : 2;
    const formatted = inMillions
      .toFixed(decimals)
      .replace(/\.0+$|(\.\d*[1-9])0+$/, "$1");
    return `${formatted}M`;
  }

  if (count >= 1_000) {
    return `${Math.floor(count / 1_000)}K`;
  }

  return String(Math.floor(count));
}

function instagramProfileUrl(username: string): string {
  const handle = String(username || "")
    .trim()
    .replace(/^@+/, "");
  if (!handle) {
    return "";
  }
  return `https://www.instagram.com/${encodeURIComponent(handle)}/`;
}

export default function ResultsPage() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<RunRecord | null>(null);
  const [finalRanked, setFinalRanked] = useState<CsvTableResult>({
    columns: [],
    rows: [],
  });
  const [reviewBucket, setReviewBucket] = useState<CsvTableResult>({
    columns: [],
    rows: [],
  });
  const [searchText, setSearchText] = useState("");
  const [tierFilter, setTierFilter] = useState<string>("all");
  const [confidenceFilter, setConfidenceFilter] = useState<string>("all");
  const [sortField, setSortField] = useState<string>("final_score");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [rowDetail, setRowDetail] = useState<Record<string, string> | null>(
    null,
  );
  const [removingRow, setRemovingRow] = useState(false);

  const refreshRuns = useCallback(async () => {
    const response = await fetch("/api/runs", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Failed to load runs.");
    }
    const payload = (await response.json()) as DashboardResponse;
    setRuns(payload.runs);

    if (!selectedRunId && payload.runs.length > 0) {
      const successful = payload.runs.find((run) => run.status === "succeeded");
      setSelectedRunId((successful || payload.runs[0]).id);
    }
  }, [selectedRunId]);

  const refreshResults = useCallback(async (runId: string) => {
    const response = await fetch(`/api/runs/${runId}/results`, {
      cache: "no-store",
    });
    if (!response.ok) {
      const payload = (await response.json()) as { error?: string };
      throw new Error(payload.error || "Failed to load results.");
    }

    const payload = (await response.json()) as ResultsResponse;
    setSelectedRun(payload.run);
    setFinalRanked(payload.finalRanked);
    setReviewBucket(payload.reviewBucket);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshRuns().catch((error) => setErrorMessage((error as Error).message));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshRuns]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    const timer = window.setTimeout(() => {
      refreshResults(selectedRunId).catch((error) =>
        setErrorMessage((error as Error).message),
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshResults, selectedRunId]);

  const tierOptions = useMemo(() => {
    const values = new Set<string>();
    for (const row of finalRanked.rows) {
      if (row.tier) {
        values.add(row.tier);
      }
    }
    return ["all", ...Array.from(values)];
  }, [finalRanked.rows]);

  const filteredRows = useMemo(() => {
    const normalizedQuery = searchText.toLowerCase().trim();

    return finalRanked.rows
      .filter((row) => {
        if (tierFilter !== "all" && row.tier !== tierFilter) {
          return false;
        }
        if (
          confidenceFilter !== "all" &&
          (row.confidence_grade || "").toLowerCase() !== confidenceFilter
        ) {
          return false;
        }
        if (!normalizedQuery) {
          return true;
        }
        return Object.values(row)
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      })
      .sort((a, b) =>
        compareValues(a[sortField] || "", b[sortField] || "", sortDirection),
      );
  }, [
    confidenceFilter,
    finalRanked.rows,
    searchText,
    sortDirection,
    sortField,
    tierFilter,
  ]);

  const toggleSort = (field: string) => {
    if (sortField === field) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection("desc");
  };

  const removeRowFromRun = async () => {
    if (!selectedRunId || !rowDetail?.username || removingRow) {
      return;
    }

    const confirmed =
      typeof window === "undefined"
        ? true
        : window.confirm(
            `Remove @${rowDetail.username} from this run's Final Ranked/Review Bucket results?`,
          );
    if (!confirmed) {
      return;
    }

    setRemovingRow(true);
    setErrorMessage(null);
    try {
      const response = await fetch(`/api/runs/${selectedRunId}/rows/remove`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username: rowDetail.username }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) {
        throw new Error(payload.error || "Failed to remove row.");
      }
      setRowDetail(null);
      await refreshResults(selectedRunId);
      await refreshRuns();
    } catch (error) {
      setErrorMessage((error as Error).message);
    } finally {
      setRemovingRow(false);
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-8">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-slate-500">
              Results Explorer
            </p>
            <h1 className="mt-1 text-xl font-semibold text-slate-900">
              Ranked Influencer Outputs
            </h1>
          </div>
          <button
            type="button"
            onClick={() =>
              refreshRuns().catch((error) =>
                setErrorMessage((error as Error).message),
              )
            }
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Refresh Runs
          </button>
        </div>

        {errorMessage ? (
          <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {errorMessage}
          </p>
        ) : null}
      </section>

      <section className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <aside className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">
            Run History
          </h2>
          <div className="mt-3 max-h-[650px] space-y-2 overflow-auto pr-1">
            {runs.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-200 p-3 text-sm text-slate-500">
                No runs found.
              </p>
            ) : (
              runs.map((run) => (
                <button
                  type="button"
                  key={run.id}
                  onClick={() => setSelectedRunId(run.id)}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${
                    selectedRunId === run.id
                      ? "border-sky-300 bg-sky-50"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <p className="font-semibold text-slate-900">
                    {run.id.slice(0, 8)}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {run.preset} · {run.status}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {new Date(run.createdAt).toLocaleString()}
                  </p>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="space-y-6">
          <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  Final Ranked Table
                </h2>
                <p className="text-xs text-slate-500">
                  {selectedRun
                    ? `Run ${selectedRun.id.slice(0, 8)} · ${selectedRun.summary.finalRankedCount} rows`
                    : "Select a run to inspect results."}
                </p>
              </div>
              {selectedRunId ? (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <a
                    href={`/api/runs/${selectedRunId}/download?file=final_ranked`}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-100"
                  >
                    Download Final Ranked
                  </a>
                  <a
                    href={`/api/runs/${selectedRunId}/download?file=review_bucket`}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-100"
                  >
                    Download Review Bucket
                  </a>
                  <a
                    href={`/api/runs/${selectedRunId}/download?file=scored`}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-100"
                  >
                    Download Scored
                  </a>
                  <a
                    href={`/api/runs/${selectedRunId}/download?file=raw_handles`}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-100"
                  >
                    Download Raw Handles
                  </a>
                  <a
                    href={`/api/runs/${selectedRunId}/download?file=enriched`}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-100"
                  >
                    Download Enriched JSON
                  </a>
                  <a
                    href={`/api/runs/${selectedRunId}/download?file=run_log`}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-100"
                  >
                    Download Run Log
                  </a>
                </div>
              ) : null}
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-[1fr_180px_180px_180px]">
              <input
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder="Search username, reasons, comments..."
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <select
                value={tierFilter}
                onChange={(event) => setTierFilter(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {tierOptions.map((tier) => (
                  <option key={tier} value={tier}>
                    {tier === "all" ? "All Tiers" : tier}
                  </option>
                ))}
              </select>
              <select
                value={confidenceFilter}
                onChange={(event) => setConfidenceFilter(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="all">All Confidence</option>
                <option value="high">High Confidence</option>
                <option value="medium">Medium Confidence</option>
                <option value="low">Low Confidence</option>
              </select>
              <select
                value={`${sortField}:${sortDirection}`}
                onChange={(event) => {
                  const [field, direction] = event.target.value.split(":");
                  setSortField(field);
                  setSortDirection(direction as "asc" | "desc");
                }}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="final_score:desc">
                  Final Score (High → Low)
                </option>
                <option value="final_score:asc">
                  Final Score (Low → High)
                </option>
                <option value="followers:desc">Followers (High → Low)</option>
                <option value="followers:asc">Followers (Low → High)</option>
                <option value="confidence_score:desc">
                  Confidence (High → Low)
                </option>
                <option value="confidence_score:asc">
                  Confidence (Low → High)
                </option>
              </select>
            </div>

            <div className="mt-4 overflow-auto rounded-xl border border-slate-200">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    {[
                      ["username", "Username"],
                      ["tier", "Tier"],
                      ["followers", "Followers"],
                      ["final_score", "Final"],
                      ["relevance_score", "Rel"],
                      ["audience_intent_score", "Intent"],
                      ["engagement_quality_score", "Eng"],
                      ["content_depth_score", "Depth"],
                      ["confidence_grade", "Conf"],
                    ].map(([field, label]) => (
                      <th
                        key={field}
                        className="cursor-pointer px-3 py-2"
                        onClick={() => toggleSort(field)}
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.length === 0 ? (
                    <tr>
                      <td className="px-3 py-4 text-slate-500" colSpan={9}>
                        No rows match this filter.
                      </td>
                    </tr>
                  ) : (
                    filteredRows.map((row, index) => (
                      <tr
                        key={`${row.username || "row"}-${index}`}
                        className="border-t border-slate-200 hover:bg-slate-50"
                      >
                        <td>
                          <button
                            type="button"
                            onClick={() => setRowDetail(row)}
                            className="px-3 py-2 font-semibold text-slate-900 hover:underline"
                          >
                            {row.username}
                          </button>
                        </td>
                        <td className="px-3 py-2">{row.tier}</td>
                        <td className="px-3 py-2">
                          {formatFollowers(row.followers)}
                        </td>
                        <td className="px-3 py-2">{row.final_score}</td>
                        <td className="px-3 py-2">{row.relevance_score}</td>
                        <td className="px-3 py-2">
                          {row.audience_intent_score}
                        </td>
                        <td className="px-3 py-2">
                          {row.engagement_quality_score}
                        </td>
                        <td className="px-3 py-2">{row.content_depth_score}</td>
                        <td className="px-3 py-2">{row.confidence_grade}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-base font-semibold text-slate-900">
              Review Bucket
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Low-confidence but promising candidates for manual evaluation.
            </p>

            <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Username</th>
                    <th className="px-3 py-2">Tier</th>
                    <th className="px-3 py-2">Final</th>
                    <th className="px-3 py-2">Review Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {reviewBucket.rows.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-3 py-4 text-slate-500">
                        Empty for this run. This means no
                        low-confidence/high-potential accounts crossed the
                        review threshold.
                      </td>
                    </tr>
                  ) : (
                    reviewBucket.rows.map((row, index) => (
                      <tr
                        key={`${row.username || "review"}-${index}`}
                        className="border-t border-slate-200"
                      >
                        <td className="px-3 py-2">{row.username}</td>
                        <td className="px-3 py-2">{row.tier}</td>
                        <td className="px-3 py-2">{row.final_score}</td>
                        <td className="px-3 py-2">{row.review_reason}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      </section>

      {rowDetail ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4"
          onClick={() => setRowDetail(null)}
        >
          <section
            className="relative max-h-[90vh] w-full max-w-5xl overflow-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              aria-label="Close detail modal"
              onClick={() => setRowDetail(null)}
              className="absolute right-3 top-3 rounded-full px-2 text-2xl leading-none text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            >
              ×
            </button>

            <div className="pr-8">
              <h2 className="text-base font-semibold text-slate-900">
                {rowDetail.username} · Detail
              </h2>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {instagramProfileUrl(rowDetail.username) ? (
                  <a
                    href={instagramProfileUrl(rowDetail.username)}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-lg border border-slate-200 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100"
                  >
                    Open Instagram Profile
                  </a>
                ) : null}
                <button
                  type="button"
                  disabled={removingRow}
                  onClick={() => void removeRowFromRun()}
                  className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1 text-xs text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {removingRow ? "Removing..." : "Remove from this list"}
                </button>
              </div>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="font-semibold text-slate-900">Why Selected</p>
                <p className="mt-2 text-slate-700">
                  {rowDetail.why_selected || "N/A"}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="font-semibold text-slate-900">Caption Evidence</p>
                <p className="mt-2 text-slate-700">
                  {rowDetail.sample_caption || "N/A"}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="font-semibold text-slate-900">Comment Evidence</p>
                <p className="mt-2 text-slate-700">
                  {rowDetail.sample_comment_1 || "N/A"}
                </p>
                <p className="mt-2 text-slate-700">
                  {rowDetail.sample_comment_2 || "N/A"}
                </p>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
