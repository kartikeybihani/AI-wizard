import { NextResponse } from "next/server";
import { z } from "zod";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

const bootstrapRequestSchema = z.object({
  limit: z.number().int().min(1).max(500).default(20),
  sourceRunId: z.string().trim().max(200).optional(),
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
    const job = await service.bootstrap(
      parsed.data.limit,
      parsed.data.sourceRunId
    );
    return NextResponse.json({ job });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message || "Bootstrap failed." },
      { status: 500 }
    );
  }
}

