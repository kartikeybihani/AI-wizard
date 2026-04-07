import { z } from "zod";

import type {
  EnrichOverrides,
  PresetName,
  RankOverrides,
  RunConfig,
  RunOverrides,
  ScoreOverrides,
  SeedOverrides,
} from "@/lib/types";

export interface StepCommand {
  name: "seed" | "enrich" | "score" | "rank";
  script: string;
  args: string[];
}

const booleanField = z.boolean().optional();
const numberField = z.number().finite().optional();
const stringField = z.string().trim().min(1).optional();

export const startRunRequestSchema = z.object({
  preset: z.enum(["short", "standard", "deep"]).default("short"),
  overrides: z
    .object({
      seed: z
        .object({
          delaySeconds: numberField,
          manualCount: numberField,
          aggregatorCount: numberField,
          hashtagLimitPerTag: numberField,
          skipApify: booleanField,
          overwrite: booleanField,
          waitSeconds: numberField,
        })
        .partial()
        .optional(),
      enrich: z
        .object({
          batchSize: numberField,
          delaySeconds: numberField,
          waitSeconds: numberField,
          minFollowersForPosts: numberField,
          maxPostAccounts: numberField,
          maxCommentAccounts: numberField,
          postsPerAccount: numberField,
          commentsPerAccount: numberField,
          commentsPerPost: numberField,
        })
        .partial()
        .optional(),
      score: z
        .object({
          model: stringField,
          maxCaptions: numberField,
          maxComments: numberField,
          minCaptions: numberField,
          minComments: numberField,
        })
        .partial()
        .optional(),
      rank: z
        .object({
          minFollowers: numberField,
          maxAccounts: numberField,
          topPerTier: numberField,
        })
        .partial()
        .optional(),
    })
    .partial()
    .optional(),
});

const PRESET_CONFIGS: Record<PresetName, Omit<RunConfig, "preset">> = {
  short: {
    seed: {
      delaySeconds: 2.5,
      manualCount: 10,
      aggregatorCount: 10,
      hashtagLimitPerTag: 5,
      skipApify: false,
      overwrite: true,
      waitSeconds: 240,
    },
    enrich: {
      batchSize: 20,
      delaySeconds: 2.5,
      waitSeconds: 240,
      minFollowersForPosts: 5000,
      maxPostAccounts: 15,
      maxCommentAccounts: 8,
      postsPerAccount: 8,
      commentsPerAccount: 20,
      commentsPerPost: 3,
    },
    score: {
      model: process.env.OPENROUTER_MODEL || "mistralai/mixtral-8x7b-instruct",
      maxCaptions: 12,
      maxComments: 20,
      minCaptions: 2,
      minComments: 4,
    },
    rank: {
      minFollowers: 5000,
      maxAccounts: 20,
      topPerTier: 0,
    },
  },
  standard: {
    seed: {
      delaySeconds: 2.5,
      manualCount: 30,
      aggregatorCount: 30,
      hashtagLimitPerTag: 20,
      skipApify: false,
      overwrite: true,
      waitSeconds: 240,
    },
    enrich: {
      batchSize: 30,
      delaySeconds: 2.5,
      waitSeconds: 240,
      minFollowersForPosts: 5000,
      maxPostAccounts: 80,
      maxCommentAccounts: 30,
      postsPerAccount: 20,
      commentsPerAccount: 40,
      commentsPerPost: 5,
    },
    score: {
      model: process.env.OPENROUTER_MODEL || "mistralai/mixtral-8x7b-instruct",
      maxCaptions: 12,
      maxComments: 20,
      minCaptions: 2,
      minComments: 4,
    },
    rank: {
      minFollowers: 5000,
      maxAccounts: 100,
      topPerTier: 0,
    },
  },
  deep: {
    seed: {
      delaySeconds: 2.5,
      manualCount: 30,
      aggregatorCount: 30,
      hashtagLimitPerTag: 60,
      skipApify: false,
      overwrite: true,
      waitSeconds: 300,
    },
    enrich: {
      batchSize: 50,
      delaySeconds: 2.5,
      waitSeconds: 300,
      minFollowersForPosts: 5000,
      maxPostAccounts: 150,
      maxCommentAccounts: 80,
      postsPerAccount: 40,
      commentsPerAccount: 120,
      commentsPerPost: 8,
    },
    score: {
      model: process.env.OPENROUTER_MODEL || "mistralai/mixtral-8x7b-instruct",
      maxCaptions: 12,
      maxComments: 20,
      minCaptions: 2,
      minComments: 4,
    },
    rank: {
      minFollowers: 5000,
      maxAccounts: 100,
      topPerTier: 0,
    },
  },
};

function mergeStep<T extends object>(base: T, override?: Partial<T>): T {
  return {
    ...base,
    ...(override || {}),
  };
}

export function buildRunConfig(preset: PresetName, overrides?: RunOverrides): RunConfig {
  const base = PRESET_CONFIGS[preset];
  return {
    preset,
    seed: mergeStep<Required<SeedOverrides>>(base.seed, overrides?.seed),
    enrich: mergeStep<Required<EnrichOverrides>>(base.enrich, overrides?.enrich),
    score: mergeStep<Required<ScoreOverrides>>(base.score, overrides?.score),
    rank: mergeStep<Required<RankOverrides>>(base.rank, overrides?.rank),
  };
}

function flag(name: string, value: boolean | number | string | undefined): string[] {
  if (value === undefined) {
    return [];
  }
  if (typeof value === "boolean") {
    return value ? [`--${name}`] : [];
  }
  return [`--${name}`, String(value)];
}

export function buildStepCommands(config: RunConfig): StepCommand[] {
  const seedArgs = [
    ...flag("output", "data/raw_handles.csv"),
    ...flag("delay-seconds", config.seed.delaySeconds),
    ...flag("manual-count", config.seed.manualCount),
    ...flag("aggregator-count", config.seed.aggregatorCount),
    ...flag("hashtag-limit-per-tag", config.seed.hashtagLimitPerTag),
    ...flag("wait-seconds", config.seed.waitSeconds),
    ...flag("skip-apify", config.seed.skipApify),
    ...flag("overwrite", config.seed.overwrite),
  ];

  const enrichArgs = [
    ...flag("input", "data/raw_handles.csv"),
    ...flag("output", "data/enriched.json"),
    ...flag("batch-size", config.enrich.batchSize),
    ...flag("delay-seconds", config.enrich.delaySeconds),
    ...flag("wait-seconds", config.enrich.waitSeconds),
    ...flag("min-followers-for-posts", config.enrich.minFollowersForPosts),
    ...flag("max-post-accounts", config.enrich.maxPostAccounts),
    ...flag("max-comment-accounts", config.enrich.maxCommentAccounts),
    ...flag("posts-per-account", config.enrich.postsPerAccount),
    ...flag("comments-per-account", config.enrich.commentsPerAccount),
    ...flag("comments-per-post", config.enrich.commentsPerPost),
  ];

  const scoreArgs = [
    ...flag("input", "data/enriched.json"),
    ...flag("output", "data/scored.csv"),
    ...flag("model", config.score.model),
    ...flag("max-captions", config.score.maxCaptions),
    ...flag("max-comments", config.score.maxComments),
    ...flag("min-captions", config.score.minCaptions),
    ...flag("min-comments", config.score.minComments),
  ];

  const rankArgs = [
    ...flag("input", "data/scored.csv"),
    ...flag("output", "data/final_ranked.csv"),
    ...flag("review-output", "data/review_bucket.csv"),
    ...flag("min-followers", config.rank.minFollowers),
    ...flag("max-accounts", config.rank.maxAccounts),
    ...flag("top-per-tier", config.rank.topPerTier),
  ];

  return [
    { name: "seed", script: "seed.py", args: seedArgs },
    { name: "enrich", script: "enrich.py", args: enrichArgs },
    { name: "score", script: "score.py", args: scoreArgs },
    { name: "rank", script: "rank.py", args: rankArgs },
  ];
}
