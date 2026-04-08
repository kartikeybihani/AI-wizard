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

export type MonitorJobKind = "bootstrap" | "run" | "schedule";
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

function nowIso(): string {
  return new Date().toISOString();
}

function ensureMonitorDbFile(): void {
  const dir = path.dirname(PIPELINE_MONITOR_DB);
  fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(PIPELINE_MONITOR_DB)) {
    const db = new Database(PIPELINE_MONITOR_DB);
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
        url TEXT
      );

      CREATE TABLE IF NOT EXISTS new_posts_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL UNIQUE,
        username TEXT NOT NULL,
        caption TEXT,
        url TEXT,
        posted_at TEXT,
        detected_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending_comment_generation'
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
    `);
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
          SELECT id, username, post_id, caption, url, posted_at, detected_at, status
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

  bootstrap(limit: number, sourceRunId?: string): Promise<MonitorJob> {
    const args = [
      "--input",
      "data/final_ranked.csv",
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

    if (options.mode === "mock") {
      args.push("--fixture", options.fixture?.trim() || "data/monitor/mock_posts.json");
      if (options.mockFailUsernames && options.mockFailUsernames.trim()) {
        args.push("--mock-fail-usernames", options.mockFailUsernames.trim());
      }
    }

    return this.runScript("run", "monitor_run.py", args);
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
