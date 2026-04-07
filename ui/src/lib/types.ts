export type PresetName = "short" | "standard" | "deep";

export type RunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type StepStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

export type RunStepName = "seed" | "enrich" | "score" | "rank";

export type RunEventType =
  | "run_started"
  | "step_started"
  | "log"
  | "step_finished"
  | "run_finished"
  | "run_failed"
  | "run_cancelled"
  | "run_queued";

export interface StepState {
  name: RunStepName;
  status: StepStatus;
  startedAt?: string;
  finishedAt?: string;
  exitCode?: number;
  command?: string;
}

export interface ArtifactPaths {
  rawHandles?: string;
  enriched?: string;
  scored?: string;
  finalRanked?: string;
  reviewBucket?: string;
  runLog: string;
}

export interface RunSummary {
  rawHandleCount: number;
  scoredCount: number;
  finalRankedCount: number;
  reviewBucketCount: number;
}

export interface SeedOverrides {
  delaySeconds?: number;
  manualCount?: number;
  aggregatorCount?: number;
  hashtagLimitPerTag?: number;
  skipApify?: boolean;
  overwrite?: boolean;
  waitSeconds?: number;
}

export interface EnrichOverrides {
  batchSize?: number;
  delaySeconds?: number;
  waitSeconds?: number;
  minFollowersForPosts?: number;
  maxPostAccounts?: number;
  maxCommentAccounts?: number;
  postsPerAccount?: number;
  commentsPerAccount?: number;
  commentsPerPost?: number;
}

export interface ScoreOverrides {
  model?: string;
  maxCaptions?: number;
  maxComments?: number;
  minCaptions?: number;
  minComments?: number;
}

export interface RankOverrides {
  minFollowers?: number;
  maxAccounts?: number;
  topPerTier?: number;
}

export interface RunOverrides {
  seed?: SeedOverrides;
  enrich?: EnrichOverrides;
  score?: ScoreOverrides;
  rank?: RankOverrides;
}

export interface StartRunRequest {
  preset: PresetName;
  overrides?: RunOverrides;
}

export interface RunConfig {
  preset: PresetName;
  seed: Required<SeedOverrides>;
  enrich: Required<EnrichOverrides>;
  score: Required<ScoreOverrides>;
  rank: Required<RankOverrides>;
}

export interface RunRecord {
  id: string;
  preset: PresetName;
  status: RunStatus;
  queueIndex: number;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  currentStep?: RunStepName;
  errorMessage?: string;
  config: RunConfig;
  steps: StepState[];
  artifacts: ArtifactPaths;
  summary: RunSummary;
}

export interface RunEvent {
  type: RunEventType;
  runId: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface CsvTableResult {
  columns: string[];
  rows: Record<string, string>[];
}
