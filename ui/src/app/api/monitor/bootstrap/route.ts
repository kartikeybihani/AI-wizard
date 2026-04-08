import { NextResponse } from "next/server";
import { z } from "zod";

import { getMonitorService, getRunService } from "@/lib/server";

export const runtime = "nodejs";

const bootstrapRequestSchema = z.object({
  limit: z.number().int().min(1).max(500).default(20),
  sourceRunId: z.string().trim().max(200).optional(),
  inputPath: z.string().trim().max(1000).optional(),
  runId: z.string().trim().max(200).optional(),
  useLatestSuccessfulRun: z.boolean().default(false),
});

export async function POST(request: Request) {
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const parsed = bootstrapRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid bootstrap payload.", issues: parsed.error.flatten() },
      { status: 400 }
    );
  }

  try {
    const service = getMonitorService();
    let sourceRunId = parsed.data.sourceRunId;
    let inputPath = parsed.data.inputPath;

    const runService = getRunService();
    const shouldResolveRun = parsed.data.useLatestSuccessfulRun || Boolean(parsed.data.runId);
    if (shouldResolveRun) {
      const runs = runService.listRuns();
      let selectedRun =
        parsed.data.runId && parsed.data.runId.trim()
          ? runs.find((run) => run.id === parsed.data.runId?.trim())
          : undefined;
      if (!selectedRun && parsed.data.useLatestSuccessfulRun) {
        selectedRun = runs.find((run) => run.status === "succeeded");
      }
      if (!selectedRun) {
        return NextResponse.json(
          { error: "No successful run found to bootstrap from." },
          { status: 400 }
        );
      }
      inputPath = selectedRun.artifacts.finalRanked;
      sourceRunId = sourceRunId || selectedRun.id;
    }

    const job = await service.bootstrap(
      parsed.data.limit,
      sourceRunId,
      inputPath
    );
    return NextResponse.json({ job });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message || "Bootstrap failed." },
      { status: 500 }
    );
  }
}
