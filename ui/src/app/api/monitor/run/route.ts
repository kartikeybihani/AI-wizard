import { NextResponse } from "next/server";
import { z } from "zod";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

const runRequestSchema = z.object({
  mode: z.enum(["live", "mock"]).default("live"),
  batchSize: z.number().int().min(1).max(50).default(25),
  postsPerAccount: z.number().int().min(1).max(10).default(5),
  limitAccounts: z.number().int().min(0).max(5000).default(20),
  delaySeconds: z.number().min(0).max(30).default(2.5),
  maxRetries: z.number().int().min(0).max(5).default(2),
  fixture: z.string().trim().max(300).optional(),
  mockFailUsernames: z.string().trim().max(1000).optional(),
});

export async function POST(request: Request) {
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const parsed = runRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid monitor run payload.", issues: parsed.error.flatten() },
      { status: 400 }
    );
  }

  try {
    const service = getMonitorService();
    const job = await service.runMonitor({
      mode: parsed.data.mode,
      batchSize: parsed.data.batchSize,
      postsPerAccount: parsed.data.postsPerAccount,
      limitAccounts: parsed.data.limitAccounts,
      delaySeconds: parsed.data.delaySeconds,
      maxRetries: parsed.data.maxRetries,
      fixture: parsed.data.fixture,
      mockFailUsernames: parsed.data.mockFailUsernames,
    });
    return NextResponse.json({ job });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message || "Monitor run failed." },
      { status: 500 }
    );
  }
}

