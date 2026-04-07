import { describe, expect, it } from "vitest";

import { buildRunConfig, buildStepCommands } from "./presets";

describe("buildRunConfig", () => {
  it("returns short preset defaults", () => {
    const config = buildRunConfig("short");
    expect(config.preset).toBe("short");
    expect(config.seed.manualCount).toBe(10);
    expect(config.enrich.maxPostAccounts).toBe(15);
    expect(config.rank.maxAccounts).toBe(20);
  });

  it("applies nested overrides without losing defaults", () => {
    const config = buildRunConfig("standard", {
      seed: { hashtagLimitPerTag: 42 },
      score: { model: "test/model-1" },
      rank: { maxAccounts: 77 },
    });

    expect(config.seed.hashtagLimitPerTag).toBe(42);
    expect(config.seed.delaySeconds).toBe(2.5);
    expect(config.score.model).toBe("test/model-1");
    expect(config.score.maxComments).toBe(20);
    expect(config.rank.maxAccounts).toBe(77);
    expect(config.rank.minFollowers).toBe(5000);
  });
});

describe("buildStepCommands", () => {
  it("maps config to python command list in step order", () => {
    const config = buildRunConfig("short", {
      seed: { manualCount: 8, skipApify: true },
      enrich: { maxPostAccounts: 11 },
      score: { maxCaptions: 9 },
      rank: { topPerTier: 3 },
    });

    const commands = buildStepCommands(config);
    expect(commands.map((step) => step.name)).toEqual([
      "seed",
      "enrich",
      "score",
      "rank",
    ]);

    const [seed, enrich, score, rank] = commands;
    expect(seed.script).toBe("seed.py");
    expect(seed.args).toEqual(expect.arrayContaining(["--manual-count", "8", "--skip-apify"]));

    expect(enrich.script).toBe("enrich.py");
    expect(enrich.args).toEqual(
      expect.arrayContaining(["--max-post-accounts", "11", "--input", "data/raw_handles.csv"])
    );

    expect(score.script).toBe("score.py");
    expect(score.args).toEqual(expect.arrayContaining(["--max-captions", "9"]));

    expect(rank.script).toBe("rank.py");
    expect(rank.args).toEqual(
      expect.arrayContaining([
        "--top-per-tier",
        "3",
        "--review-output",
        "data/review_bucket.csv",
      ])
    );
  });
});
