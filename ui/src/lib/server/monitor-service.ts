import fs from "node:fs";
import { randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import path from "node:path";

import Database from "better-sqlite3";

import {
  PIPELINE_CWD,
  PIPELINE_MONITOR_DB,
  ensureServerDirectories,
} from "@/lib/server/config";

export type MonitorJobKind = "bootstrap" | "run" | "schedule" | "generate";
export type MonitorJobStatus = "running" | "succeeded" | "failed";

export interface MonitorJob {
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

export interface MonitorOverview {
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

export interface EngageSuggestion {
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

export interface EngagePostCard {
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

function nowIso(): string {
  return new Date().toISOString();
}

function toIsoOrEmpty(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) {
    return "";
  }
  return value;
}

function buildInstagramEmbedUrl(url: string): string {
  const cleaned = String(url || "").trim();
  if (!cleaned) {
    return "";
  }
  try {
    const parsed = new URL(cleaned);
    const match = parsed.pathname.match(/^\/(reel|p|tv)\/([^/?#]+)/i);
    if (!match) {
      return cleaned;
    }
    return `https://www.instagram.com/${match[1].toLowerCase()}/${match[2]}/embed`;
  } catch {
    return cleaned;
  }
}

function ensureColumn(db: Database.Database, tableName: string, columnName: string, ddlFragment: string): void {
  const rows = db.prepare(`PRAGMA table_info(${tableName})`).all() as Array<{ name: string }>;
  const hasColumn = rows.some((row) => row.name === columnName);
  if (hasColumn) {
    return;
  }
  db.exec(`ALTER TABLE ${tableName} ADD COLUMN ${ddlFragment}`);
}

function ensureMonitorDbFile(): void {
  const dir = path.dirname(PIPELINE_MONITOR_DB);
  fs.mkdirSync(dir, { recursive: true });
  const db = new Database(PIPELINE_MONITOR_DB);
  try {
    db.exec(`
      CREATE TABLE IF NOT EXISTS tracked_accounts (
        username TEXT PRIMARY KEY,
        tier TEXT,
        final_score REAL,
        active INTEGER NOT NULL DEFAULT 1,
        source_run_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS seen_posts (
        post_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        posted_at TEXT,
        first_seen_at TEXT NOT NULL,
        caption TEXT,
        url TEXT,
        is_video INTEGER NOT NULL DEFAULT 0,
        media_type TEXT NOT NULL DEFAULT 'unknown'
      );

      CREATE TABLE IF NOT EXISTS new_posts_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL UNIQUE,
        username TEXT NOT NULL,
        caption TEXT,
        url TEXT,
        posted_at TEXT,
        detected_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending_comment_generation',
        is_video INTEGER NOT NULL DEFAULT 0,
        media_type TEXT NOT NULL DEFAULT 'unknown'
      );

      CREATE TABLE IF NOT EXISTS monitor_runs (
        run_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        accounts_checked INTEGER NOT NULL DEFAULT 0,
        new_posts_found INTEGER NOT NULL DEFAULT 0,
        failed_accounts INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        error_summary TEXT
      );

      CREATE TABLE IF NOT EXISTS post_processing (
        post_id TEXT PRIMARY KEY,
        queue_id INTEGER,
        status TEXT NOT NULL,
        transcript_text TEXT,
        transcript_source TEXT,
        transcript_model TEXT,
        post_context_json TEXT,
        generation_json TEXT,
        critic_json TEXT,
        selected_suggestion_id INTEGER,
        error_message TEXT,
        processing_started_at TEXT,
        processing_finished_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS comment_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL,
        label TEXT NOT NULL,
        comment TEXT NOT NULL,
        why_it_works TEXT,
        risk_level TEXT,
        critic_score REAL,
        critic_json TEXT,
        decision_status TEXT NOT NULL DEFAULT 'pending',
        edited_comment TEXT,
        final_comment TEXT,
        decision_reason TEXT,
        decision_at TEXT,
        submitted_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(post_id, label)
      );

      CREATE INDEX IF NOT EXISTS idx_new_posts_queue_status_detected
      ON new_posts_queue(status, detected_at DESC);

      CREATE INDEX IF NOT EXISTS idx_seen_posts_username
      ON seen_posts(username);

      CREATE INDEX IF NOT EXISTS idx_post_processing_status
      ON post_processing(status, updated_at DESC);

      CREATE INDEX IF NOT EXISTS idx_comment_suggestions_post
      ON comment_suggestions(post_id, decision_status, updated_at DESC);
    `);

    ensureColumn(db, "seen_posts", "is_video", "is_video INTEGER NOT NULL DEFAULT 0");
    ensureColumn(db, "seen_posts", "media_type", "media_type TEXT NOT NULL DEFAULT 'unknown'");
    ensureColumn(db, "new_posts_queue", "is_video", "is_video INTEGER NOT NULL DEFAULT 0");
    ensureColumn(db, "new_posts_queue", "media_type", "media_type TEXT NOT NULL DEFAULT 'unknown'");
  } finally {
    db.close();
  }
}

function trimLogs(lines: string[], max = 600): string[] {
  if (lines.length <= max) {
    return lines;
  }
  return lines.slice(lines.length - max);
}

export class MonitorService {
  private activeJob: MonitorJob | null = null;
  private recentJobs: MonitorJob[] = [];

  constructor() {
    ensureServerDirectories();
    ensureMonitorDbFile();
  }

  private readOverviewFromDb(): Omit<
    MonitorOverview,
    "activeJob" | "recentJobs"
  > {
    ensureMonitorDbFile();
    const db = new Database(PIPELINE_MONITOR_DB, { readonly: true });
    try {
      const trackedCount = Number(
        (
          db
            .prepare("SELECT COUNT(*) AS count FROM tracked_accounts")
            .get() as { count: number }
        ).count || 0
      );
      const seenPostsCount = Number(
        (
          db
            .prepare("SELECT COUNT(*) AS count FROM seen_posts")
            .get() as { count: number }
        ).count || 0
      );
      const queueCount = Number(
        (
          db
            .prepare("SELECT COUNT(*) AS count FROM new_posts_queue")
            .get() as { count: number }
        ).count || 0
      );
      const pendingQueueCount = Number(
        (
          db
            .prepare(
              "SELECT COUNT(*) AS count FROM new_posts_queue WHERE status = 'pending_comment_generation'"
            )
            .get() as { count: number }
        ).count || 0
      );
      const runsCount = Number(
        (
          db
            .prepare("SELECT COUNT(*) AS count FROM monitor_runs")
            .get() as { count: number }
        ).count || 0
      );

      const recentQueue = db
        .prepare(
          `
          SELECT id, username, post_id, caption, url, posted_at, detected_at, status, is_video, media_type
          FROM new_posts_queue
          ORDER BY detected_at DESC
          LIMIT 120
          `
        )
        .all() as Array<{
        id: number;
        username: string;
        post_id: string;
        caption: string | null;
        url: string | null;
        posted_at: string | null;
        detected_at: string;
        status: string;
        is_video: number;
        media_type: string;
      }>;

      const recentSeenPosts = db
        .prepare(
          `
          SELECT username, post_id, url, posted_at, first_seen_at, caption
          FROM seen_posts
          ORDER BY first_seen_at DESC
          LIMIT 120
          `
        )
        .all() as Array<{
        username: string;
        post_id: string;
        url: string | null;
        posted_at: string | null;
        first_seen_at: string;
        caption: string | null;
      }>;

      const recentRuns = db
        .prepare(
          `
          SELECT run_id, mode, started_at, ended_at, accounts_checked, new_posts_found, failed_accounts, status, error_summary
          FROM monitor_runs
          ORDER BY started_at DESC
          LIMIT 40
          `
        )
        .all() as Array<{
        run_id: string;
        mode: string;
        started_at: string;
        ended_at: string | null;
        accounts_checked: number;
        new_posts_found: number;
        failed_accounts: number;
        status: string;
        error_summary: string | null;
      }>;

      const trackedAccounts = db
        .prepare(
          `
          SELECT username, tier, final_score, active, updated_at
          FROM tracked_accounts
          ORDER BY active DESC, COALESCE(final_score, -1) DESC, username ASC
          LIMIT 120
          `
        )
        .all() as Array<{
        username: string;
        tier: string | null;
        final_score: number | null;
        active: number;
        updated_at: string;
      }>;

      return {
        trackedCount,
        seenPostsCount,
        queueCount,
        pendingQueueCount,
        runsCount,
        recentQueue: recentQueue.map((row) => ({
          id: row.id,
          username: row.username,
          postId: row.post_id,
          caption: row.caption || "",
          url: row.url || "",
          postedAt: row.posted_at || "",
          detectedAt: row.detected_at,
          status: row.status,
          isVideo: Number(row.is_video || 0),
          mediaType: row.media_type || "unknown",
        })),
        recentSeenPosts: recentSeenPosts.map((row) => ({
          username: row.username,
          postId: row.post_id,
          url: row.url || "",
          postedAt: row.posted_at || "",
          firstSeenAt: row.first_seen_at,
          caption: row.caption || "",
        })),
        recentRuns: recentRuns.map((row) => ({
          runId: row.run_id,
          mode: row.mode,
          startedAt: row.started_at,
          endedAt: row.ended_at || "",
          accountsChecked: Number(row.accounts_checked || 0),
          newPostsFound: Number(row.new_posts_found || 0),
          failedAccounts: Number(row.failed_accounts || 0),
          status: row.status,
          errorSummary: row.error_summary || "",
        })),
        trackedAccounts: trackedAccounts.map((row) => ({
          username: row.username,
          tier: row.tier || "",
          finalScore:
            typeof row.final_score === "number" && Number.isFinite(row.final_score)
              ? row.final_score
              : null,
          active: Number(row.active || 0),
          updatedAt: row.updated_at,
        })),
      };
    } finally {
      db.close();
    }
  }

  getOverview(): MonitorOverview {
    return {
      ...this.readOverviewFromDb(),
      activeJob: this.activeJob ? { ...this.activeJob, logs: [...this.activeJob.logs] } : null,
      recentJobs: this.recentJobs.map((job) => ({ ...job, logs: [...job.logs] })),
    };
  }

  getJob(jobId: string): MonitorJob | null {
    if (this.activeJob?.id === jobId) {
      return { ...this.activeJob, logs: [...this.activeJob.logs] };
    }
    const job = this.recentJobs.find((item) => item.id === jobId);
    return job ? { ...job, logs: [...job.logs] } : null;
  }

  private pushCompletedJob(job: MonitorJob): void {
    this.recentJobs = [job, ...this.recentJobs].slice(0, 20);
  }

  private async runScript(kind: MonitorJobKind, script: string, args: string[]): Promise<MonitorJob> {
    if (this.activeJob && this.activeJob.status === "running") {
      throw new Error(
        `Monitor job already running (${this.activeJob.kind}, ${this.activeJob.id.slice(0, 8)}).`
      );
    }

    const id = randomUUID();
    const command = `python3 ${script} ${args.join(" ")}`.trim();
    const job: MonitorJob = {
      id,
      kind,
      status: "running",
      command,
      startedAt: nowIso(),
      logs: [],
    };
    this.activeJob = job;

    await new Promise<void>((resolve) => {
      const child = spawn("python3", [script, ...args], {
        cwd: PIPELINE_CWD,
        env: process.env,
      });

      child.stdout.on("data", (chunk: Buffer) => {
        const text = chunk.toString("utf-8").replace(/\r/g, "");
        const lines = text.split("\n").filter(Boolean);
        if (lines.length === 0 || !this.activeJob) {
          return;
        }
        this.activeJob.logs = trimLogs([...this.activeJob.logs, ...lines], 600);
      });

      child.stderr.on("data", (chunk: Buffer) => {
        const text = chunk.toString("utf-8").replace(/\r/g, "");
        const lines = text.split("\n").filter(Boolean).map((line) => `[stderr] ${line}`);
        if (lines.length === 0 || !this.activeJob) {
          return;
        }
        this.activeJob.logs = trimLogs([...this.activeJob.logs, ...lines], 600);
      });

      child.on("close", (code) => {
        const exitCode = typeof code === "number" ? code : 1;
        if (this.activeJob) {
          this.activeJob.status = exitCode === 0 ? "succeeded" : "failed";
          this.activeJob.exitCode = exitCode;
          this.activeJob.finishedAt = nowIso();
          if (exitCode !== 0 && !this.activeJob.errorMessage) {
            this.activeJob.errorMessage = `Command failed with exit code ${exitCode}.`;
          }

          const completed = { ...this.activeJob, logs: [...this.activeJob.logs] };
          this.pushCompletedJob(completed);
          this.activeJob = null;
        }
        resolve();
      });

      child.on("error", (error) => {
        if (this.activeJob) {
          this.activeJob.status = "failed";
          this.activeJob.exitCode = 1;
          this.activeJob.finishedAt = nowIso();
          this.activeJob.errorMessage = error.message;
          const completed = { ...this.activeJob, logs: [...this.activeJob.logs] };
          this.pushCompletedJob(completed);
          this.activeJob = null;
        }
        resolve();
      });
    });

    const result = this.getJob(id);
    if (!result) {
      throw new Error("Monitor job finished but could not be loaded.");
    }
    return result;
  }

  bootstrap(limit: number, sourceRunId?: string, inputPath?: string): Promise<MonitorJob> {
    const args = [
      "--input",
      inputPath?.trim() || "data/final_ranked.csv",
      "--limit",
      String(limit),
    ];
    if (sourceRunId && sourceRunId.trim()) {
      args.push("--source-run-id", sourceRunId.trim());
    }
    return this.runScript("bootstrap", "monitor_bootstrap.py", args);
  }

  runMonitor(options: {
    mode: "live" | "mock";
    batchSize: number;
    postsPerAccount: number;
    limitAccounts: number;
    delaySeconds: number;
    maxRetries: number;
    fixture?: string;
    mockFailUsernames?: string;
    autoGenerateComments?: boolean;
    generateLimit?: number;
    whisperModel?: string;
  }): Promise<MonitorJob> {
    const args = [
      "--mode",
      options.mode,
      "--batch-size",
      String(options.batchSize),
      "--posts-per-account",
      String(options.postsPerAccount),
      "--limit-accounts",
      String(options.limitAccounts),
      "--delay-seconds",
      String(options.delaySeconds),
      "--max-retries",
      String(options.maxRetries),
    ];
    if (typeof options.autoGenerateComments === "boolean") {
      args.push(options.autoGenerateComments ? "--auto-generate-comments" : "--no-auto-generate-comments");
    }
    if (typeof options.generateLimit === "number" && Number.isFinite(options.generateLimit)) {
      args.push("--generate-limit", String(Math.max(1, Math.floor(options.generateLimit))));
    }
    if (options.whisperModel && options.whisperModel.trim()) {
      args.push("--whisper-model", options.whisperModel.trim());
    }

    if (options.mode === "mock") {
      args.push("--fixture", options.fixture?.trim() || "data/monitor/mock_posts.json");
      if (options.mockFailUsernames && options.mockFailUsernames.trim()) {
        args.push("--mock-fail-usernames", options.mockFailUsernames.trim());
      }
    }

    return this.runScript("run", "monitor_run.py", args);
  }

  runGenerate(options: {
    limit: number;
    postIds?: string[];
    whisperModel?: string;
    model?: string;
    force?: boolean;
    characterBible?: string;
  }): Promise<MonitorJob> {
    const args = [
      "--db-path",
      PIPELINE_MONITOR_DB,
      "--limit",
      String(Math.max(1, Math.floor(options.limit || 10))),
    ];
    if (options.postIds && options.postIds.length > 0) {
      const cleaned = options.postIds.map((postId) => postId.trim()).filter(Boolean);
      if (cleaned.length > 0) {
        args.push("--post-ids", cleaned.join(","));
      }
    }
    if (options.whisperModel && options.whisperModel.trim()) {
      args.push("--whisper-model", options.whisperModel.trim());
    }
    if (options.model && options.model.trim()) {
      args.push("--model", options.model.trim());
    }
    if (options.force) {
      args.push("--force");
    }
    if (options.characterBible && options.characterBible.trim()) {
      args.push("--character-bible", options.characterBible.trim());
    }
    return this.runScript("generate", "engage_generate.py", args);
  }

  getEngagePosts(options?: { status?: string; limit?: number }): EngagePostCard[] {
    ensureMonitorDbFile();
    const db = new Database(PIPELINE_MONITOR_DB, { readonly: true });
    try {
      const rawStatus = options?.status;
      const statuses =
        typeof rawStatus === "undefined"
          ? ["ready_for_review"]
          : String(rawStatus)
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean);
      const safeLimit = Math.max(1, Math.min(100, Number(options?.limit || 10)));

      const whereParts: string[] = [];
      const params: Array<string | number> = [];
      if (statuses.length > 0) {
        const placeholders = statuses.map(() => "?").join(", ");
        whereParts.push(`q.status IN (${placeholders})`);
        params.push(...statuses);
      }
      const whereClause = whereParts.length > 0 ? `WHERE ${whereParts.join(" AND ")}` : "";

      const queueRows = db
        .prepare(
          `
          SELECT
            q.id AS queue_id,
            q.post_id,
            q.username,
            q.caption,
            q.url,
            q.posted_at,
            q.detected_at,
            q.status,
            q.is_video,
            q.media_type,
            pp.transcript_text,
            pp.transcript_source,
            pp.transcript_model,
            pp.error_message,
            pp.processing_started_at,
            pp.processing_finished_at,
            pp.selected_suggestion_id
          FROM new_posts_queue q
          LEFT JOIN post_processing pp ON pp.post_id = q.post_id
          ${whereClause}
          ORDER BY q.detected_at DESC
          LIMIT ?
          `
        )
        .all(...params, safeLimit) as Array<{
        queue_id: number;
        post_id: string;
        username: string;
        caption: string | null;
        url: string | null;
        posted_at: string | null;
        detected_at: string;
        status: string;
        is_video: number;
        media_type: string | null;
        transcript_text: string | null;
        transcript_source: string | null;
        transcript_model: string | null;
        error_message: string | null;
        processing_started_at: string | null;
        processing_finished_at: string | null;
        selected_suggestion_id: number | null;
      }>;

      const postIds = queueRows.map((row) => row.post_id).filter(Boolean);
      const suggestionsByPostId = new Map<string, EngageSuggestion[]>();
      if (postIds.length > 0) {
        const placeholders = postIds.map(() => "?").join(", ");
        const suggestionRows = db
          .prepare(
            `
            SELECT
              id,
              post_id,
              label,
              comment,
              why_it_works,
              risk_level,
              critic_score,
              decision_status,
              edited_comment,
              final_comment,
              decision_reason,
              decision_at,
              submitted_at
            FROM comment_suggestions
            WHERE post_id IN (${placeholders})
            ORDER BY post_id ASC, created_at ASC, id ASC
            `
          )
          .all(...postIds) as Array<{
          id: number;
          post_id: string;
          label: string;
          comment: string;
          why_it_works: string | null;
          risk_level: string | null;
          critic_score: number | null;
          decision_status: string;
          edited_comment: string | null;
          final_comment: string | null;
          decision_reason: string | null;
          decision_at: string | null;
          submitted_at: string | null;
        }>;
        for (const row of suggestionRows) {
          const bucket = suggestionsByPostId.get(row.post_id) || [];
          bucket.push({
            id: Number(row.id),
            postId: row.post_id,
            label: row.label,
            comment: row.comment,
            whyItWorks: row.why_it_works || "",
            riskLevel: row.risk_level || "",
            criticScore:
              typeof row.critic_score === "number" && Number.isFinite(row.critic_score)
                ? row.critic_score
                : null,
            decisionStatus: row.decision_status || "pending",
            editedComment: row.edited_comment || "",
            finalComment: row.final_comment || "",
            decisionReason: row.decision_reason || "",
            decisionAt: toIsoOrEmpty(row.decision_at),
            submittedAt: toIsoOrEmpty(row.submitted_at),
            isSelected: false,
          });
          suggestionsByPostId.set(row.post_id, bucket);
        }
      }

      return queueRows.map((row) => {
        const suggestions = suggestionsByPostId.get(row.post_id) || [];
        const selectedId = typeof row.selected_suggestion_id === "number" ? row.selected_suggestion_id : null;
        const withSelected = suggestions.map((suggestion) => ({
          ...suggestion,
          isSelected: selectedId !== null && suggestion.id === selectedId,
        }));
        return {
          queueId: Number(row.queue_id),
          postId: row.post_id,
          username: row.username,
          caption: row.caption || "",
          url: row.url || "",
          embedUrl: buildInstagramEmbedUrl(row.url || ""),
          postedAt: toIsoOrEmpty(row.posted_at),
          detectedAt: row.detected_at,
          status: row.status,
          isVideo: Number(row.is_video || 0),
          mediaType: row.media_type || "unknown",
          transcriptText: row.transcript_text || "",
          transcriptSource: row.transcript_source || "",
          transcriptModel: row.transcript_model || "",
          errorMessage: row.error_message || "",
          processingStartedAt: toIsoOrEmpty(row.processing_started_at),
          processingFinishedAt: toIsoOrEmpty(row.processing_finished_at),
          selectedSuggestionId: selectedId,
          suggestions: withSelected,
        };
      });
    } finally {
      db.close();
    }
  }

  getEngageStatusCounts(): Record<string, number> {
    ensureMonitorDbFile();
    const db = new Database(PIPELINE_MONITOR_DB, { readonly: true });
    try {
      const rows = db
        .prepare(
          `
          SELECT status, COUNT(*) AS count
          FROM new_posts_queue
          GROUP BY status
          `
        )
        .all() as Array<{ status: string; count: number }>;
      const out: Record<string, number> = {};
      for (const row of rows) {
        out[row.status] = Number(row.count || 0);
      }
      return out;
    } finally {
      db.close();
    }
  }

  approveSuggestion(suggestionId: number, editedText?: string): {
    postId: string;
    queueId: number;
    suggestionId: number;
    finalComment: string;
  } {
    ensureMonitorDbFile();
    const db = new Database(PIPELINE_MONITOR_DB);
    const now = nowIso();
    try {
      const row = db
        .prepare(
          `
          SELECT cs.id, cs.post_id, cs.comment, nq.id AS queue_id
          FROM comment_suggestions cs
          JOIN new_posts_queue nq ON nq.post_id = cs.post_id
          WHERE cs.id = ?
          LIMIT 1
          `
        )
        .get(suggestionId) as
        | {
            id: number;
            post_id: string;
            comment: string;
            queue_id: number;
          }
        | undefined;
      if (!row) {
        throw new Error("Suggestion not found.");
      }

      const finalComment = (editedText || "").trim() || row.comment;
      const tx = db.transaction(() => {
        db.prepare(
          `
          UPDATE comment_suggestions
          SET decision_status = 'pending',
              updated_at = ?
          WHERE post_id = ?
            AND id <> ?
            AND decision_status IN ('approved', 'submitted')
          `
        ).run(now, row.post_id, row.id);

        db.prepare(
          `
          UPDATE comment_suggestions
          SET decision_status = 'approved',
              edited_comment = ?,
              final_comment = ?,
              decision_reason = '',
              decision_at = ?,
              submitted_at = NULL,
              updated_at = ?
          WHERE id = ?
          `
        ).run((editedText || "").trim(), finalComment, now, now, row.id);

        db.prepare(`UPDATE new_posts_queue SET status = 'approved' WHERE post_id = ?`).run(row.post_id);

        db.prepare(
          `
          INSERT INTO post_processing (
            post_id, queue_id, status, selected_suggestion_id, created_at, updated_at
          ) VALUES (?, ?, 'approved', ?, ?, ?)
          ON CONFLICT(post_id) DO UPDATE SET
            queue_id = excluded.queue_id,
            status = excluded.status,
            selected_suggestion_id = excluded.selected_suggestion_id,
            updated_at = excluded.updated_at
          `
        ).run(row.post_id, row.queue_id, row.id, now, now);
      });
      tx();

      return {
        postId: row.post_id,
        queueId: Number(row.queue_id),
        suggestionId: Number(row.id),
        finalComment,
      };
    } finally {
      db.close();
    }
  }

  rejectSuggestion(suggestionId: number, reason?: string): {
    postId: string;
    queueId: number;
    suggestionId: number;
  } {
    ensureMonitorDbFile();
    const db = new Database(PIPELINE_MONITOR_DB);
    const now = nowIso();
    try {
      const row = db
        .prepare(
          `
          SELECT cs.id, cs.post_id, nq.id AS queue_id
          FROM comment_suggestions cs
          JOIN new_posts_queue nq ON nq.post_id = cs.post_id
          WHERE cs.id = ?
          LIMIT 1
          `
        )
        .get(suggestionId) as
        | {
            id: number;
            post_id: string;
            queue_id: number;
          }
        | undefined;
      if (!row) {
        throw new Error("Suggestion not found.");
      }

      const tx = db.transaction(() => {
        db.prepare(
          `
          UPDATE comment_suggestions
          SET decision_status = 'rejected',
              decision_reason = ?,
              decision_at = ?,
              updated_at = ?
          WHERE id = ?
          `
        ).run((reason || "").trim(), now, now, row.id);

        db.prepare(`UPDATE new_posts_queue SET status = 'rejected' WHERE post_id = ?`).run(row.post_id);

        db.prepare(
          `
          INSERT INTO post_processing (
            post_id, queue_id, status, error_message, created_at, updated_at
          ) VALUES (?, ?, 'rejected', ?, ?, ?)
          ON CONFLICT(post_id) DO UPDATE SET
            queue_id = excluded.queue_id,
            status = excluded.status,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
          `
        ).run(row.post_id, row.queue_id, (reason || "").trim(), now, now);
      });
      tx();

      return {
        postId: row.post_id,
        queueId: Number(row.queue_id),
        suggestionId: Number(row.id),
      };
    } finally {
      db.close();
    }
  }

  submitPost(queueId: number): {
    queueId: number;
    postId: string;
    suggestionId: number;
    finalComment: string;
    username: string;
    url: string;
  } {
    ensureMonitorDbFile();
    const db = new Database(PIPELINE_MONITOR_DB);
    const now = nowIso();
    try {
      const queueRow = db
        .prepare(
          `
          SELECT q.id, q.post_id, q.username, q.url, pp.selected_suggestion_id
          FROM new_posts_queue q
          LEFT JOIN post_processing pp ON pp.post_id = q.post_id
          WHERE q.id = ?
          LIMIT 1
          `
        )
        .get(queueId) as
        | {
            id: number;
            post_id: string;
            username: string;
            url: string | null;
            selected_suggestion_id: number | null;
          }
        | undefined;

      if (!queueRow) {
        throw new Error("Post queue item not found.");
      }

      const submitted = db
        .prepare(
          `
          SELECT id, comment, edited_comment, final_comment
          FROM comment_suggestions
          WHERE post_id = ?
            AND decision_status = 'submitted'
          ORDER BY submitted_at DESC, updated_at DESC
          LIMIT 1
          `
        )
        .get(queueRow.post_id) as
        | {
            id: number;
            comment: string;
            edited_comment: string | null;
            final_comment: string | null;
          }
        | undefined;

      let chosen =
        submitted ||
        (db
          .prepare(
            `
            SELECT id, comment, edited_comment, final_comment
            FROM comment_suggestions
            WHERE post_id = ?
              AND decision_status = 'approved'
            ORDER BY decision_at DESC, updated_at DESC
            LIMIT 1
            `
          )
          .get(queueRow.post_id) as
          | {
              id: number;
              comment: string;
              edited_comment: string | null;
              final_comment: string | null;
            }
          | undefined);

      if (!chosen && typeof queueRow.selected_suggestion_id === "number") {
        chosen = db
          .prepare(
            `
            SELECT id, comment, edited_comment, final_comment
            FROM comment_suggestions
            WHERE id = ? AND post_id = ?
            LIMIT 1
            `
          )
          .get(queueRow.selected_suggestion_id, queueRow.post_id) as
          | {
              id: number;
              comment: string;
              edited_comment: string | null;
              final_comment: string | null;
            }
          | undefined;
      }

      if (!chosen) {
        chosen = db
          .prepare(
            `
            SELECT id, comment, edited_comment, final_comment
            FROM comment_suggestions
            WHERE post_id = ?
            ORDER BY COALESCE(critic_score, -1) DESC, id ASC
            LIMIT 1
            `
          )
          .get(queueRow.post_id) as
          | {
              id: number;
              comment: string;
              edited_comment: string | null;
              final_comment: string | null;
            }
          | undefined;
      }

      if (!chosen) {
        throw new Error("No suggestion available to submit.");
      }

      const chosenSuggestion = chosen;
      const finalComment =
        (chosenSuggestion.edited_comment || "").trim() ||
        (chosenSuggestion.final_comment || "").trim() ||
        chosenSuggestion.comment;
      const tx = db.transaction(() => {
        db.prepare(
          `
          UPDATE comment_suggestions
          SET decision_status = 'submitted',
              final_comment = ?,
              submitted_at = ?,
              decision_at = COALESCE(decision_at, ?),
              updated_at = ?
          WHERE id = ?
          `
        ).run(finalComment, now, now, now, chosenSuggestion.id);

        db.prepare(`UPDATE new_posts_queue SET status = 'submitted' WHERE id = ?`).run(queueId);

        db.prepare(
          `
          INSERT INTO post_processing (
            post_id, queue_id, status, selected_suggestion_id, processing_finished_at, created_at, updated_at
          ) VALUES (?, ?, 'submitted', ?, ?, ?, ?)
          ON CONFLICT(post_id) DO UPDATE SET
            queue_id = excluded.queue_id,
            status = excluded.status,
            selected_suggestion_id = excluded.selected_suggestion_id,
            processing_finished_at = excluded.processing_finished_at,
            updated_at = excluded.updated_at
          `
        ).run(queueRow.post_id, queueId, chosenSuggestion.id, now, now, now);
      });
      tx();

      return {
        queueId: Number(queueRow.id),
        postId: queueRow.post_id,
        suggestionId: Number(chosenSuggestion.id),
        finalComment,
        username: queueRow.username,
        url: queueRow.url || "",
      };
    } finally {
      db.close();
    }
  }

  ensureSchedule(options: {
    name: string;
    cron: string;
    timezone: string;
    disable?: boolean;
    actorTaskId?: string;
    actorId?: string;
    runInput?: string;
  }): Promise<MonitorJob> {
    const args = [
      "--ensure",
      "--name",
      options.name.trim(),
      "--cron",
      options.cron.trim(),
      "--timezone",
      options.timezone.trim(),
    ];
    if (options.disable) {
      args.push("--disable");
    }
    if (options.actorTaskId && options.actorTaskId.trim()) {
      args.push("--actor-task-id", options.actorTaskId.trim());
    }
    if (options.actorId && options.actorId.trim()) {
      args.push("--actor-id", options.actorId.trim());
    }
    if (options.runInput && options.runInput.trim()) {
      args.push("--run-input", options.runInput.trim());
    }
    return this.runScript("schedule", "monitor_schedule.py", args);
  }
}
