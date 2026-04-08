import { NextResponse } from "next/server";
import { z } from "zod";

import { getRunService } from "@/lib/server";

export const runtime = "nodejs";

const removeRowRequestSchema = z.object({
  username: z.string().trim().min(1).max(100),
});

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const parsed = removeRowRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid payload.", issues: parsed.error.flatten() },
      { status: 400 }
    );
  }

  let service = getRunService() as ReturnType<typeof getRunService> & {
    removeUsernameFromRunResults?: (
      runId: string,
      username: string
    ) =>
      | {
          removedFromFinalRanked: number;
          removedFromReviewBucket: number;
          summary: unknown;
        }
      | null;
  };

  // In dev, hot reload can keep an older singleton instance alive.
  if (typeof service.removeUsernameFromRunResults !== "function") {
    (globalThis as { __tomsRunService?: unknown }).__tomsRunService = undefined;
    service = getRunService() as typeof service;
  }

  if (typeof service.removeUsernameFromRunResults !== "function") {
    return NextResponse.json(
      { error: "Run service is stale. Restart dev server and retry." },
      { status: 500 }
    );
  }

  const result = service.removeUsernameFromRunResults(id, parsed.data.username);
  if (!result) {
    return NextResponse.json({ error: "Run not found." }, { status: 404 });
  }

  return NextResponse.json({ result });
}
