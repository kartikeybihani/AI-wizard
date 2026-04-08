"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type EngageStatusFilter =
  | "all"
  | "ready_for_review"
  | "pending_comment_generation"
  | "transcribing"
  | "generation_failed"
  | "submitted"
  | "approved"
  | "rejected";

interface MonitorJob {
  id: string;
  kind: "bootstrap" | "run" | "schedule" | "generate";
  status: "running" | "succeeded" | "failed";
  command: string;
  startedAt: string;
  finishedAt?: string;
  exitCode?: number;
  logs: string[];
  errorMessage?: string;
}

interface EngageSuggestion {
  id: number;
  postId: string;
  label: string;
  comment: string;
  whyItWorks: string;
  riskLevel: string;
  criticScore: number | null;
  decisionStatus: string;
  editedComment: string;
  finalComment: string;
  decisionReason: string;
  decisionAt: string;
  submittedAt: string;
  isSelected: boolean;
}

interface EngagePostCard {
  queueId: number;
  postId: string;
  username: string;
  caption: string;
  url: string;
  embedUrl: string;
  postedAt: string;
  detectedAt: string;
  status: string;
  isVideo: number;
  mediaType: string;
  transcriptText: string;
  transcriptSource: string;
  transcriptModel: string;
  errorMessage: string;
  processingStartedAt: string;
  processingFinishedAt: string;
  selectedSuggestionId: number | null;
  suggestions: EngageSuggestion[];
}

function classForStatus(status: string): string {
  switch (status) {
    case "ready_for_review":
      return "bg-emerald-100 text-emerald-700";
    case "approved":
      return "bg-blue-100 text-blue-700";
    case "rejected":
    case "generation_failed":
      return "bg-rose-100 text-rose-700";
    case "submitted":
      return "bg-violet-100 text-violet-700";
    case "transcribing":
      return "bg-amber-100 text-amber-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

const FILTER_OPTIONS: Array<{ key: EngageStatusFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "ready_for_review", label: "Ready" },
  { key: "pending_comment_generation", label: "Pending" },
  { key: "transcribing", label: "Transcribing" },
  { key: "approved", label: "Approved" },
  { key: "generation_failed", label: "Failed" },
  { key: "submitted", label: "Submitted" },
];

function extractJobMetric(logs: string[], metric: "processed" | "success" | "failed"): number {
  const joined = logs.join(" ");
  const match = joined.match(new RegExp(`${metric}=(\\d+)`));
  return match ? Number(match[1]) : 0;
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

export default function EngagePage() {
  const [posts, setPosts] = useState<EngagePostCard[]>([]);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [selectedPostId, setSelectedPostId] = useState<string>("");
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<number | null>(null);
  const [editedText, setEditedText] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<EngageStatusFilter>("all");
  const [limit, setLimit] = useState<number>(10);
  const [generateBatchSize, setGenerateBatchSize] = useState<number>(10);
  const [drainMaxBatches, setDrainMaxBatches] = useState<number>(20);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [successMessage, setSuccessMessage] = useState<string>("");
  const [busyAction, setBusyAction] = useState<string>("");
  const [lastJob, setLastJob] = useState<MonitorJob | null>(null);
  const [approvePulse, setApprovePulse] = useState(false);

  const refreshPosts = useCallback(async () => {
    const response = await fetch(
      `/api/engage/posts?status=${encodeURIComponent(statusFilter)}&limit=${encodeURIComponent(String(limit))}`,
      { cache: "no-store" }
    );
    const payload = (await response.json()) as {
      posts?: EngagePostCard[];
      statusCounts?: Record<string, number>;
      error?: string;
    };
    if (!response.ok) {
      throw new Error(payload.error || "Failed to load engage posts.");
    }
    const incoming = Array.isArray(payload.posts) ? payload.posts : [];
    setStatusCounts(payload.statusCounts || {});
    setPosts(incoming);
    setSelectedPostId((previous) => {
      if (previous && incoming.some((item) => item.postId === previous)) {
        return previous;
      }
      return incoming[0]?.postId || "";
    });
  }, [limit, statusFilter]);

  useEffect(() => {
    let mounted = true;
    refreshPosts().catch((error) => {
      if (mounted) {
        setErrorMessage((error as Error).message);
      }
    });
    const timer = setInterval(() => {
      refreshPosts().catch((error) => {
        if (mounted) {
          setErrorMessage((error as Error).message);
        }
      });
    }, 8000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [refreshPosts]);

  const selectedPost = useMemo(
    () => posts.find((post) => post.postId === selectedPostId) || null,
    [posts, selectedPostId]
  );

  const bestSuggestionId = useMemo(() => {
    if (!selectedPost) {
      return null;
    }
    const explicit = selectedPost.suggestions.find((item) => item.isSelected);
    if (explicit) {
      return explicit.id;
    }
    const approved = selectedPost.suggestions.find((item) => item.decisionStatus === "approved");
    if (approved) {
      return approved.id;
    }
    return selectedPost.suggestions[0]?.id || null;
  }, [selectedPost]);

  useEffect(() => {
    if (!selectedPost) {
      setSelectedSuggestionId(null);
      setEditedText("");
      return;
    }
    const activeSuggestionId = bestSuggestionId;
    setSelectedSuggestionId(activeSuggestionId);
    const suggestion = selectedPost.suggestions.find((item) => item.id === activeSuggestionId);
    if (!suggestion) {
      setEditedText("");
      return;
    }
    setEditedText(
      suggestion.finalComment.trim() || suggestion.editedComment.trim() || suggestion.comment.trim()
    );
  }, [bestSuggestionId, selectedPost]);

  const activeSuggestion = useMemo(() => {
    if (!selectedPost || selectedSuggestionId === null) {
      return null;
    }
    return selectedPost.suggestions.find((item) => item.id === selectedSuggestionId) || null;
  }, [selectedPost, selectedSuggestionId]);

  const totalAcrossStatuses = useMemo(
    () => Object.values(statusCounts).reduce((sum, value) => sum + Number(value || 0), 0),
    [statusCounts]
  );

  const totalForCurrentFilter = useMemo(() => {
    if (statusFilter === "all") {
      return totalAcrossStatuses;
    }
    return Number(statusCounts[statusFilter] || 0);
  }, [statusCounts, statusFilter, totalAcrossStatuses]);

  const runAction = useCallback(
    async (actionName: string, work: () => Promise<void>) => {
      setBusyAction(actionName);
      setErrorMessage("");
      setSuccessMessage("");
      try {
        await work();
        await refreshPosts();
      } catch (error) {
        setErrorMessage((error as Error).message);
      } finally {
        setBusyAction("");
      }
    },
    [refreshPosts]
  );

  const handleApprove = async () => {
    if (!activeSuggestion) {
      return;
    }
    const selectedIndex = posts.findIndex((post) => post.postId === selectedPostId);
    const nextPostId =
      selectedIndex >= 0
        ? posts[selectedIndex + 1]?.postId || posts[selectedIndex - 1]?.postId || ""
        : "";
    await runAction("approve", async () => {
      await postJson(`/api/engage/suggestions/${activeSuggestion.id}/approve`, {
        editedText: editedText.trim() || undefined,
      });
      setSuccessMessage("Suggestion approved.");
    });
    if (nextPostId) {
      setSelectedPostId(nextPostId);
    }
    setApprovePulse(true);
    setTimeout(() => setApprovePulse(false), 900);
  };

  const handleReject = async () => {
    if (!activeSuggestion) {
      return;
    }
    await runAction("reject", async () => {
      await postJson(`/api/engage/suggestions/${activeSuggestion.id}/reject`, {});
      setSuccessMessage("Suggestion rejected.");
    });
  };

  const handleSubmitAndCopy = async () => {
    if (!selectedPost) {
      return;
    }
    await runAction("submit", async () => {
      const payload = await postJson<{ result: { finalComment: string } }>(
        `/api/engage/posts/${selectedPost.queueId}/submit`,
        {}
      );
      const finalComment = payload.result?.finalComment || "";
      if (finalComment && typeof navigator !== "undefined" && navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(finalComment);
          setSuccessMessage("Submitted and copied to clipboard.");
          return;
        } catch {
          // noop; still show final text in success message below.
        }
      }
      setSuccessMessage(`Submitted. Copy this comment: ${finalComment}`);
    });
  };

  const handleRegenerate = async () => {
    if (!selectedPost) {
      return;
    }
    await runAction("regenerate", async () => {
      const payload = await postJson<{ job: MonitorJob }>("/api/engage/generate", {
        limit: 1,
        postIds: [selectedPost.postId],
        force: true,
      });
      setLastJob(payload.job);
      if (payload.job.status === "failed") {
        throw new Error(
          payload.job.errorMessage ||
            payload.job.logs.slice(-3).join(" | ") ||
            "Regeneration job failed."
        );
      }
      const tail = payload.job.logs.slice(-2).join(" | ");
      setSuccessMessage(
        tail
          ? `Regeneration completed: ${tail}`
          : "Regeneration completed. Refreshing queue."
      );
    });
  };

  const handleClearQueue = async () => {
    const confirmed =
      typeof window === "undefined"
        ? true
        : window.confirm(
            "Clear all Engage queue items and generated suggestions? This keeps tracked accounts and monitor runs."
          );
    if (!confirmed) {
      return;
    }

    await runAction("clear-queue", async () => {
      const payload = await postJson<{
        result: {
          queueCleared: number;
          processingCleared: number;
          suggestionsCleared: number;
          seenPostsCleared: number;
        };
      }>("/api/engage/reset", {
        clearSeenPosts: false,
      });
      setLastJob(null);
      const result = payload.result || {
        queueCleared: 0,
        processingCleared: 0,
        suggestionsCleared: 0,
      };
      setSuccessMessage(
        `Cleared queue=${result.queueCleared}, processing=${result.processingCleared}, suggestions=${result.suggestionsCleared}.`
      );
    });
  };

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-8">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-slate-500">Part 4 Engage</p>
            <h1 className="mt-1 text-xl font-semibold text-slate-900">Reels Review and Comment Actions</h1>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-600">
              Visible Cards
              <input
                type="number"
                min={1}
                max={100}
                value={limit}
                onChange={(event) => setLimit(Math.max(1, Math.min(100, Number(event.target.value) || 10)))}
                className="ml-2 w-20 rounded-lg border border-slate-300 px-2 py-1 text-sm text-slate-900"
              />
            </label>
            <button
              type="button"
              onClick={() => refreshPosts().catch((error) => setErrorMessage((error as Error).message))}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              Refresh
            </button>
            <button
              type="button"
              disabled={busyAction !== ""}
              onClick={() => void handleClearQueue()}
              className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {busyAction === "clear-queue" ? "Clearing..." : "Clear Queue"}
            </button>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {FILTER_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setStatusFilter(option.key)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                statusFilter === option.key
                  ? "bg-slate-900 text-white"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
              }`}
            >
              {option.label}
              {option.key !== "all"
                ? ` (${statusCounts[option.key] || 0})`
                : ` (${totalAcrossStatuses})`}
            </button>
          ))}
        </div>
        {errorMessage ? (
          <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {errorMessage}
          </p>
        ) : null}
        {successMessage ? (
          <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {successMessage}
          </p>
        ) : null}
        {lastJob ? (
          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <p className="font-semibold text-slate-800">
              Last Generate Job: {lastJob.status} (exit {typeof lastJob.exitCode === "number" ? lastJob.exitCode : "-"})
            </p>
            <p className="mt-1 break-all text-slate-600">{lastJob.command}</p>
            {lastJob.logs.length > 0 ? (
              <p className="mt-1 text-slate-600">{lastJob.logs.slice(-2).join(" | ")}</p>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.4fr_0.8fr_1fr]">
        <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Review Queue</h2>
          <div className="mt-2 flex items-center justify-between">
            <p className="text-xs text-slate-500">
              Showing {posts.length} of {totalForCurrentFilter}
            </p>
            {totalForCurrentFilter > limit && limit < 100 ? (
              <button
                type="button"
                onClick={() => setLimit(Math.max(1, Math.min(100, totalForCurrentFilter)))}
                className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-100"
              >
                Show All
              </button>
            ) : null}
          </div>
          <div className="mt-3 max-h-[70vh] overflow-auto rounded-xl border border-slate-200">
            {(posts || []).length === 0 ? (
              <p className="p-4 text-sm text-slate-500">
                No posts in this view yet. Try All, then run Monitor, then Generate Next.
              </p>
            ) : (
              <ul className="divide-y divide-slate-200">
                {posts.map((post) => (
                  <li key={post.postId}>
                    <button
                      type="button"
                      onClick={() => setSelectedPostId(post.postId)}
                      className={`w-full px-3 py-3 text-left ${
                        selectedPostId === post.postId ? "bg-slate-100" : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-semibold text-slate-900">@{post.username}</p>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] ${classForStatus(post.status)}`}>
                          {post.status}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs text-slate-600">
                        {(post.caption || "No caption available.").slice(0, 160)}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-500">
                        posted: {post.postedAt ? new Date(post.postedAt).toLocaleString() : "-"} · detected:{" "}
                        {post.detectedAt ? new Date(post.detectedAt).toLocaleString() : "-"}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!selectedPost || busyAction !== ""}
                onClick={() => void handleRegenerate()}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100"
              >
                {busyAction === "regenerate" ? "Retrying..." : "Retry Selected"}
              </button>
              <button
                type="button"
                disabled={busyAction !== ""}
                onClick={() =>
                  void runAction("generate-next", async () => {
                    const payload = await postJson<{ job: MonitorJob }>("/api/engage/generate", {
                      limit: generateBatchSize,
                      includeFailed: false,
                    });
                    setLastJob(payload.job);
                    if (payload.job.status === "failed") {
                      throw new Error(
                        payload.job.errorMessage ||
                          payload.job.logs.slice(-3).join(" | ") ||
                          "Generate Next job failed."
                      );
                    }
                    const processed = extractJobMetric(payload.job.logs, "processed");
                    if (processed > 0) {
                      setLimit((previous) => Math.min(100, previous + processed));
                    }
                    const tail = payload.job.logs.slice(-2).join(" | ");
                    setSuccessMessage(
                      tail
                        ? `Generate job completed: ${tail}`
                        : `Generated next ${generateBatchSize} pending posts.`
                    );
                  })
                }
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100"
              >
                {busyAction === "generate-next" ? "Generating..." : `Generate Next ${generateBatchSize}`}
              </button>
              <button
                type="button"
                disabled={busyAction !== ""}
                onClick={() =>
                  void runAction("drain-pending", async () => {
                    const payload = await postJson<{ job: MonitorJob }>("/api/engage/generate", {
                      limit: generateBatchSize,
                      includeFailed: false,
                      drainPending: true,
                      maxBatches: drainMaxBatches,
                    });
                    setLastJob(payload.job);
                    if (payload.job.status === "failed") {
                      throw new Error(
                        payload.job.errorMessage ||
                          payload.job.logs.slice(-3).join(" | ") ||
                          "Drain pending job failed."
                      );
                    }
                    const processed = extractJobMetric(payload.job.logs, "processed");
                    if (processed > 0) {
                      setLimit((previous) => Math.min(100, previous + processed));
                    }
                    const tail = payload.job.logs.slice(-2).join(" | ");
                    setSuccessMessage(
                      tail
                        ? `Drain completed: ${tail}`
                        : `Processed up to ${drainMaxBatches} passes of ${generateBatchSize}.`
                    );
                  })
                }
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100"
              >
                {busyAction === "drain-pending" ? "Generating..." : "Generate Remaining"}
              </button>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <label className="flex items-center justify-between text-xs text-slate-600">
                Batch Size
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={generateBatchSize}
                  onChange={(event) =>
                    setGenerateBatchSize(Math.max(1, Math.min(50, Number(event.target.value) || 10)))
                  }
                  className="ml-2 w-20 rounded-lg border border-slate-300 px-2 py-1 text-sm text-slate-900"
                />
              </label>
              <label className="flex items-center justify-between text-xs text-slate-600">
                Max Passes
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={drainMaxBatches}
                  onChange={(event) =>
                    setDrainMaxBatches(Math.max(1, Math.min(200, Number(event.target.value) || 20)))
                  }
                  className="ml-2 w-20 rounded-lg border border-slate-300 px-2 py-1 text-sm text-slate-900"
                />
              </label>
            </div>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Preview</h2>
          {!selectedPost ? (
            <p className="mt-3 text-sm text-slate-500">Select a post from the queue.</p>
          ) : (
            <div className="mt-3 space-y-3">
              {selectedPost.embedUrl ? (
                <iframe
                  src={selectedPost.embedUrl}
                  title={`Instagram post ${selectedPost.postId}`}
                  className="h-[78vh] min-h-[640px] max-h-[920px] w-full rounded-xl border border-slate-200 bg-white"
                  loading="lazy"
                />
              ) : null}
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Caption</p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
                  {selectedPost.caption ? selectedPost.caption.slice(0, 1200) : "No caption available."}
                </p>
              </div>
              {selectedPost.errorMessage ? (
                <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                  Generation Error: {selectedPost.errorMessage}
                </p>
              ) : null}
              <a
                href={selectedPost.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex text-sm font-medium text-sky-700 hover:underline"
              >
                Open Reel
              </a>
            </div>
          )}
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Blake Comment Suggestions</h2>
          {!selectedPost ? (
            <p className="mt-3 text-sm text-slate-500">Select a post from the queue.</p>
          ) : (
            <>
              <div className="mt-3 space-y-2">
                {selectedPost.suggestions.length === 0 ? (
                  <p className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
                    No suggestions yet for this post.
                  </p>
                ) : (
                  selectedPost.suggestions.map((suggestion) => {
                    const active = selectedSuggestionId === suggestion.id;
                    return (
                      <button
                        key={suggestion.id}
                        type="button"
                        onClick={() => {
                          setSelectedSuggestionId(suggestion.id);
                          setEditedText(
                            suggestion.finalComment.trim() ||
                              suggestion.editedComment.trim() ||
                              suggestion.comment.trim()
                          );
                        }}
                        className={`w-full rounded-xl border p-3 text-left ${
                          active
                            ? "border-slate-900 bg-slate-50"
                            : "border-slate-200 bg-white hover:border-slate-300"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            {suggestion.label}
                            {suggestion.isSelected ? " · best pick" : ""}
                          </p>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] ${classForStatus(suggestion.decisionStatus)}`}>
                            {suggestion.decisionStatus}
                          </span>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-800">{suggestion.comment}</p>
                        <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-500">
                          <span>risk: {suggestion.riskLevel || "-"}</span>
                          <span>
                            critic:{" "}
                            {typeof suggestion.criticScore === "number"
                              ? suggestion.criticScore.toFixed(2)
                              : "-"}
                          </span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>

              <div className="mt-4 rounded-xl border border-slate-200 p-3">
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Edit Final Comment
                </label>
                <textarea
                  rows={6}
                  value={editedText}
                  onChange={(event) => setEditedText(event.target.value)}
                  className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                  placeholder="Edit the selected candidate before approval..."
                />
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={!activeSuggestion || busyAction !== ""}
                    onClick={() => void handleApprove()}
                    className={`rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white transition-all hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-400 ${
                      approvePulse ? "scale-[1.02] ring-2 ring-emerald-300 shadow-[0_0_0_3px_rgba(52,211,153,0.25)]" : ""
                    }`}
                  >
                    {busyAction === "approve" ? "Approving..." : approvePulse ? "Approved ✓" : "Approve"}
                  </button>
                  <button
                    type="button"
                    disabled={!activeSuggestion || busyAction !== ""}
                    onClick={() => void handleReject()}
                    className="rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white hover:bg-rose-500 disabled:cursor-not-allowed disabled:bg-slate-400"
                  >
                    {busyAction === "reject" ? "Rejecting..." : "Reject"}
                  </button>
                  <button
                    type="button"
                    disabled={busyAction !== ""}
                    onClick={() => void handleSubmitAndCopy()}
                    className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                  >
                    {busyAction === "submit" ? "Submitting..." : "Submit & Copy"}
                  </button>
                </div>
              </div>
            </>
          )}
        </article>
      </section>
    </main>
  );
}
