import { describe, expect, it } from "vitest";

import { selectRunsForPrune } from "./run-service";

describe("selectRunsForPrune", () => {
  it("returns empty list when below retention limit", () => {
    const runIds = ["run-3", "run-2", "run-1"];
    expect(selectRunsForPrune(runIds, 30)).toEqual([]);
  });

  it("returns oldest ids beyond retention limit", () => {
    const runIds = Array.from({ length: 35 }, (_, index) => `run-${35 - index}`);
    const toDelete = selectRunsForPrune(runIds, 30);

    expect(toDelete.length).toBe(5);
    expect(toDelete).toEqual(["run-5", "run-4", "run-3", "run-2", "run-1"]);
  });
});
