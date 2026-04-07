import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

import Database from "better-sqlite3";
import kill from "tree-kill";

import type {
  ArtifactPaths,
  CsvTableResult,
  PresetName,
  RunConfig,
  RunEvent,
  RunOverrides,
  RunRecord,
  RunStatus,
  RunSummary,
  RunStepName,
  StepState,
  StepStatus,
} from "@/lib/types";
import { countCsvRows, parseCsv } from "@/lib/server/csv";
import {
  buildRunConfig,
  buildStepCommands,
  type StepCommand,
} from "@/lib/server/presets";
import {
  DB_PATH,
  PIPELINE_CWD,
  PIPELINE_DATA_DIR,
  PIPELINE_RUNS_DIR,
  RETENTION_LIMIT,
  ensureServerDirectories,
} from "@/lib/server/config";

interface RunDataBlob {
  config: RunConfig;
  steps: StepState[];
  artifacts: ArtifactPaths;
  summary: RunSummary;
  errorMessage?: string;
}

interface RunRow {
  id: string;
  preset: PresetName;
  status: RunStatus;
  queue_index: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  current_step: RunStepName | null;
  data_json: string;
}

interface ActiveProcess {
  runId: string;
  child: ChildProcessWithoutNullStreams;
}

function nowIso(): string {
  return new Date().toISOString();
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function summarizeArtifacts(artifacts: ArtifactPaths): RunSummary {
  return {
    rawHandleCount: countCsvRows(artifacts.rawHandles),
    scoredCount: countCsvRows(artifacts.scored),
    finalRankedCount: countCsvRows(artifacts.finalRanked),
    reviewBucketCount: countCsvRows(artifacts.reviewBucket),
  };
}

export function selectRunsForPrune(
  runIdsNewestFirst: string[],
  retentionLimit: number
): string[] {
  if (runIdsNewestFirst.length <= retentionLimit) {
    return [];
  }
  return runIdsNewestFirst.slice(retentionLimit);
}

function ensureFile(pathname: string): void {
  fs.mkdirSync(path.dirname(pathname), { recursive: true });
  if (!fs.existsSync(pathname)) {
    fs.writeFileSync(pathname, "", "utf-8");
  }
}

function terminateProcess(pid: number): Promise<void> {
  return new Promise((resolve) => {
    kill(pid, "SIGTERM", () => resolve());
  });
}

function initialSteps(commands: StepCommand[]): StepState[] {
  return commands.map((command) => ({
    name: command.name,
    status: "pending",
    command: `python3 ${command.script} ${command.args.join(" ")}`,
  }));
}

export class RunService {
  private db: Database.Database;
  private emitter = new EventEmitter();
  private activeRunId: string | null = null;
  private activeProcess: ActiveProcess | null = null;
  private queue: string[] = [];
  private cancelRequested = new Set<string>();
  private queueLoopActive = false;

  constructor() {
    ensureServerDirectories();
    this.db = new Database(DB_PATH);
    this.db.pragma("journal_mode = WAL");
    this.createTables();
    this.recoverInterruptedRuns();
    this.loadQueue();
    this.emittersTuning();
    this.kickQueueLoop();
  }

  private emittersTuning(): void {
    this.emitter.setMaxListeners(200);
  }

  private createTables(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        preset TEXT NOT NULL,
        status TEXT NOT NULL,
        queue_index INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        current_step TEXT,
        data_json TEXT NOT NULL
      );
    `);
  }

  private recoverInterruptedRuns(): void {
    const stamp = nowIso();
    const rows = this.db
      .prepare("SELECT * FROM runs WHERE status IN ('running', 'queued')")
      .all() as RunRow[];

    for (const row of rows) {
      const run = this.rowToRun(row);
      run.status = "failed";
      run.finishedAt = stamp;
      run.currentStep = undefined;
      run.errorMessage = "Service restarted before this run completed.";
      run.queueIndex = 0;
      for (const step of run.steps) {
        if (step.status === "running" || step.status === "pending") {
          step.status = "cancelled";
          step.finishedAt = stamp;
        }
      }
      this.saveRun(run);
    }
  }

  private loadQueue(): void {
    const rows = this.db
      .prepare(
        "SELECT id FROM runs WHERE status = 'queued' ORDER BY queue_index ASC, created_at ASC"
      )
      .all() as { id: string }[];
    this.queue = rows.map((row) => row.id);
    this.persistQueueIndexes();
  }

  private rowToRun(row: RunRow): RunRecord {
    const data = JSON.parse(row.data_json) as RunDataBlob;
    return {
      id: row.id,
      preset: row.preset,
      status: row.status,
      queueIndex: row.queue_index,
      createdAt: row.created_at,
      startedAt: row.started_at || undefined,
      finishedAt: row.finished_at || undefined,
      currentStep: row.current_step || undefined,
      config: data.config,
      steps: data.steps,
      artifacts: data.artifacts,
      summary: data.summary,
      errorMessage: data.errorMessage,
    };
  }

  private toDataBlob(run: RunRecord): RunDataBlob {
    return {
      config: run.config,
      steps: run.steps,
      artifacts: run.artifacts,
      summary: run.summary,
      errorMessage: run.errorMessage,
    };
  }

  private saveRun(run: RunRecord): void {
    const stmt = this.db.prepare(`
      INSERT INTO runs (
        id, preset, status, queue_index, created_at,
        started_at, finished_at, current_step, data_json
      ) VALUES (
        @id, @preset, @status, @queue_index, @created_at,
        @started_at, @finished_at, @current_step, @data_json
      )
      ON CONFLICT(id) DO UPDATE SET
        preset = excluded.preset,
        status = excluded.status,
        queue_index = excluded.queue_index,
        created_at = excluded.created_at,
        started_at = excluded.started_at,
        finished_at = excluded.finished_at,
        current_step = excluded.current_step,
        data_json = excluded.data_json
    `);

    stmt.run({
      id: run.id,
      preset: run.preset,
      status: run.status,
      queue_index: run.queueIndex,
      created_at: run.createdAt,
      started_at: run.startedAt || null,
      finished_at: run.finishedAt || null,
      current_step: run.currentStep || null,
      data_json: JSON.stringify(this.toDataBlob(run)),
    });
  }

  private getRunInternal(id: string): RunRecord | null {
    const row = this.db.prepare("SELECT * FROM runs WHERE id = ?").get(id) as
      | RunRow
      | undefined;
    return row ? this.rowToRun(row) : null;
  }

  private persistQueueIndexes(): void {
    const update = this.db.prepare("UPDATE runs SET queue_index = ? WHERE id = ?");
    this.queue.forEach((id, index) => {
      update.run(index + 1, id);
    });
  }

  private emitEvent(type: RunEvent["type"], runId: string, payload: Record<string, unknown>): void {
    const event: RunEvent = {
      type,
      runId,
      timestamp: nowIso(),
      payload,
    };
    this.emitter.emit(`run:${runId}`, event);
  }

  private appendLog(run: RunRecord, step: RunStepName, stream: "stdout" | "stderr", text: string): void {
    if (!text) {
      return;
    }
    ensureFile(run.artifacts.runLog);
    const lines = text.replace(/\r/g, "").split("\n").filter(Boolean);
    for (const line of lines) {
      const entry = `[${nowIso()}] [${step}] [${stream}] ${line}\n`;
      fs.appendFileSync(run.artifacts.runLog, entry, "utf-8");
      this.emitEvent("log", run.id, {
        step,
        stream,
        text: line,
      });
    }
  }

  private updateStepStatus(
    run: RunRecord,
    stepName: RunStepName,
    status: StepStatus,
    exitCode?: number
  ): void {
    const step = run.steps.find((item) => item.name === stepName);
    if (!step) {
      return;
    }

    if (status === "running") {
      step.startedAt = nowIso();
    }
    if (status === "succeeded" || status === "failed" || status === "cancelled") {
      step.finishedAt = nowIso();
    }

    step.status = status;
    if (exitCode !== undefined) {
      step.exitCode = exitCode;
    }
  }

  private async executeStep(run: RunRecord, command: StepCommand): Promise<number> {
    return await new Promise<number>((resolve) => {
      const child = spawn("python3", [command.script, ...command.args], {
        cwd: PIPELINE_CWD,
        env: process.env,
      });

      this.activeProcess = {
        runId: run.id,
        child,
      };

      child.stdout.on("data", (chunk: Buffer) => {
        this.appendLog(run, command.name, "stdout", chunk.toString());
      });

      child.stderr.on("data", (chunk: Buffer) => {
        this.appendLog(run, command.name, "stderr", chunk.toString());
      });

      child.on("error", (error) => {
        this.appendLog(run, command.name, "stderr", `Spawn error: ${error.message}`);
        resolve(1);
      });

      child.on("close", (code) => {
        if (this.cancelRequested.has(run.id)) {
          resolve(130);
          return;
        }
        resolve(typeof code === "number" ? code : 1);
      });
    });
  }

  private async materializeArtifacts(run: RunRecord): Promise<ArtifactPaths> {
    const destinationDir = path.join(PIPELINE_RUNS_DIR, run.id);
    fs.mkdirSync(destinationDir, { recursive: true });

    const copyMap: Array<[keyof ArtifactPaths, string]> = [
      ["rawHandles", "raw_handles.csv"],
      ["enriched", "enriched.json"],
      ["scored", "scored.csv"],
      ["finalRanked", "final_ranked.csv"],
      ["reviewBucket", "review_bucket.csv"],
    ];

    const artifacts: ArtifactPaths = {
      runLog: run.artifacts.runLog,
    };

    for (const [key, filename] of copyMap) {
      const source = path.join(PIPELINE_DATA_DIR, filename);
      const destination = path.join(destinationDir, filename);
      if (fs.existsSync(source)) {
        fs.copyFileSync(source, destination);
        artifacts[key] = destination;
      }
    }

    return artifacts;
  }

  private async executeRun(runId: string): Promise<void> {
    const run = this.getRunInternal(runId);
    if (!run) {
      return;
    }

    try {
      run.status = "running";
      run.startedAt = run.startedAt || nowIso();
      run.currentStep = undefined;
      run.queueIndex = 0;
      this.saveRun(run);
      this.emitEvent("run_started", run.id, {
        preset: run.preset,
      });

      const commands = buildStepCommands(run.config);
      for (const command of commands) {
        if (this.cancelRequested.has(run.id)) {
          throw new Error("RUN_CANCELLED");
        }

        run.currentStep = command.name;
        this.updateStepStatus(run, command.name, "running");
        this.saveRun(run);
        this.emitEvent("step_started", run.id, {
          step: command.name,
          command: `python3 ${command.script} ${command.args.join(" ")}`,
        });

        const exitCode = await this.executeStep(run, command);
        this.activeProcess = null;

        if (this.cancelRequested.has(run.id) || exitCode === 130) {
          throw new Error("RUN_CANCELLED");
        }

        if (exitCode !== 0) {
          this.updateStepStatus(run, command.name, "failed", exitCode);
          run.status = "failed";
          run.finishedAt = nowIso();
          run.errorMessage = `Step '${command.name}' failed with exit code ${exitCode}.`;
          run.currentStep = undefined;
          this.saveRun(run);
          this.emitEvent("run_failed", run.id, {
            step: command.name,
            exitCode,
            error: run.errorMessage,
          });
          return;
        }

        this.updateStepStatus(run, command.name, "succeeded", exitCode);
        this.saveRun(run);
        this.emitEvent("step_finished", run.id, {
          step: command.name,
          exitCode,
        });
      }

      run.artifacts = await this.materializeArtifacts(run);
      run.summary = summarizeArtifacts(run.artifacts);
      run.status = "succeeded";
      run.finishedAt = nowIso();
      run.currentStep = undefined;
      run.errorMessage = undefined;
      this.saveRun(run);
      this.emitEvent("run_finished", run.id, {
        summary: run.summary,
      });
    } catch (error) {
      this.activeProcess = null;

      if ((error as Error).message === "RUN_CANCELLED") {
        run.status = "cancelled";
        run.finishedAt = nowIso();
        run.currentStep = undefined;
        run.errorMessage = "Run was cancelled by the operator.";
        run.steps
          .filter((item) => item.status === "running" || item.status === "pending")
          .forEach((item) => {
            item.status = "cancelled";
            item.finishedAt = nowIso();
          });
        this.saveRun(run);
        this.emitEvent("run_cancelled", run.id, {
          message: run.errorMessage,
        });
      } else {
        run.status = "failed";
        run.finishedAt = nowIso();
        run.currentStep = undefined;
        run.errorMessage = (error as Error).message;
        this.saveRun(run);
        this.emitEvent("run_failed", run.id, {
          error: run.errorMessage,
        });
      }
    } finally {
      this.cancelRequested.delete(run.id);
      this.activeRunId = null;
      this.pruneRetention();
      this.kickQueueLoop();
    }
  }

  private kickQueueLoop(): void {
    if (this.queueLoopActive || this.activeRunId) {
      return;
    }

    this.queueLoopActive = true;
    void (async () => {
      try {
        while (!this.activeRunId && this.queue.length > 0) {
          const nextRunId = this.queue.shift();
          this.persistQueueIndexes();
          if (!nextRunId) {
            continue;
          }
          this.activeRunId = nextRunId;
          await this.executeRun(nextRunId);
        }
      } finally {
        this.queueLoopActive = false;
      }
    })();
  }

  private pruneRetention(): void {
    const rows = this.db
      .prepare(
        `
          SELECT id
          FROM runs
          WHERE status IN ('succeeded', 'failed', 'cancelled')
          ORDER BY datetime(COALESCE(finished_at, created_at)) DESC
        `
      )
      .all() as { id: string }[];

    const idsToDelete = selectRunsForPrune(
      rows.map((row) => row.id),
      RETENTION_LIMIT
    );
    const remove = this.db.prepare("DELETE FROM runs WHERE id = ?");

    for (const id of idsToDelete) {
      remove.run(id);
      fs.rmSync(path.join(PIPELINE_RUNS_DIR, id), {
        recursive: true,
        force: true,
      });
      this.queue = this.queue.filter((queuedId) => queuedId !== id);
    }
    this.persistQueueIndexes();
  }

  createRun(preset: PresetName, overrides?: RunOverrides): RunRecord {
    const runId = randomUUID();
    const config = buildRunConfig(preset, overrides);
    const commands = buildStepCommands(config);
    const runFolder = path.join(PIPELINE_RUNS_DIR, runId);
    const runLog = path.join(runFolder, "run.log");

    fs.mkdirSync(runFolder, { recursive: true });
    fs.writeFileSync(runLog, "", "utf-8");

    const run: RunRecord = {
      id: runId,
      preset,
      status: this.activeRunId ? "queued" : "running",
      queueIndex: this.activeRunId ? this.queue.length + 1 : 0,
      createdAt: nowIso(),
      startedAt: this.activeRunId ? undefined : nowIso(),
      finishedAt: undefined,
      currentStep: undefined,
      config,
      steps: initialSteps(commands),
      artifacts: {
        runLog,
      },
      summary: {
        rawHandleCount: 0,
        scoredCount: 0,
        finalRankedCount: 0,
        reviewBucketCount: 0,
      },
    };

    this.saveRun(run);

    if (run.status === "queued") {
      this.queue.push(run.id);
      this.persistQueueIndexes();
      this.emitEvent("run_queued", run.id, {
        queueIndex: run.queueIndex,
      });
      this.kickQueueLoop();
    } else {
      this.activeRunId = run.id;
      void this.executeRun(run.id);
    }

    return clone(run);
  }

  async cancelRun(runId: string): Promise<RunRecord | null> {
    const run = this.getRunInternal(runId);
    if (!run) {
      return null;
    }

    if (run.status === "queued") {
      run.status = "cancelled";
      run.finishedAt = nowIso();
      run.errorMessage = "Run was cancelled before execution.";
      run.queueIndex = 0;
      run.steps.forEach((step) => {
        if (step.status === "pending") {
          step.status = "cancelled";
          step.finishedAt = nowIso();
        }
      });
      this.queue = this.queue.filter((id) => id !== runId);
      this.persistQueueIndexes();
      this.saveRun(run);
      this.emitEvent("run_cancelled", run.id, {
        message: run.errorMessage,
      });
      return run;
    }

    if (run.status === "running" && this.activeProcess?.runId === runId) {
      this.cancelRequested.add(runId);
      const pid = this.activeProcess.child.pid;
      if (typeof pid === "number") {
        await terminateProcess(pid);
      }
      return this.getRunInternal(runId);
    }

    return run;
  }

  listRuns(): RunRecord[] {
    const rows = this.db
      .prepare("SELECT * FROM runs ORDER BY datetime(created_at) DESC")
      .all() as RunRow[];
    return rows.map((row) => this.rowToRun(row));
  }

  getRun(runId: string): RunRecord | null {
    const run = this.getRunInternal(runId);
    return run ? clone(run) : null;
  }

  getDashboardState(): {
    activeRunId: string | null;
    queuedRunIds: string[];
    runs: RunRecord[];
  } {
    return {
      activeRunId: this.activeRunId,
      queuedRunIds: [...this.queue],
      runs: this.listRuns(),
    };
  }

  getLogTail(runId: string, maxLines = 300): string[] {
    const run = this.getRunInternal(runId);
    if (!run || !run.artifacts.runLog || !fs.existsSync(run.artifacts.runLog)) {
      return [];
    }

    const text = fs.readFileSync(run.artifacts.runLog, "utf-8");
    const lines = text.split(/\r?\n/).filter(Boolean);
    return lines.slice(-maxLines);
  }

  getResults(runId: string): {
    run: RunRecord;
    finalRanked: CsvTableResult;
    reviewBucket: CsvTableResult;
  } | null {
    const run = this.getRunInternal(runId);
    if (!run) {
      return null;
    }

    return {
      run,
      finalRanked: parseCsv(run.artifacts.finalRanked),
      reviewBucket: parseCsv(run.artifacts.reviewBucket),
    };
  }

  getDownloadPath(runId: string, artifact: keyof ArtifactPaths): string | null {
    const run = this.getRunInternal(runId);
    if (!run) {
      return null;
    }

    const artifactPath = run.artifacts[artifact];
    if (!artifactPath || !fs.existsSync(artifactPath)) {
      return null;
    }
    return artifactPath;
  }

  subscribe(runId: string, handler: (event: RunEvent) => void): () => void {
    const eventName = `run:${runId}`;
    this.emitter.on(eventName, handler);
    return () => {
      this.emitter.off(eventName, handler);
    };
  }
}
