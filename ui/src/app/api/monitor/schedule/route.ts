import { NextResponse } from "next/server";
import { z } from "zod";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

const scheduleRequestSchema = z.object({
  name: z.string().trim().min(1).max(120).default("toms-part2-monitor-4h"),
  cron: z.string().trim().min(1).max(60).default("0 */4 * * *"),
  timezone: z.string().trim().min(1).max(120).default("America/Phoenix"),
  disable: z.boolean().optional().default(false),
  actorTaskId: z.string().trim().max(120).optional(),
  actorId: z.string().trim().max(120).optional(),
  runInput: z.string().trim().max(4000).optional(),
});

export async function POST(request: Request) {
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const parsed = scheduleRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid schedule payload.", issues: parsed.error.flatten() },
      { status: 400 }
    );
  }

  try {
    const service = getMonitorService();
    const job = await service.ensureSchedule({
      name: parsed.data.name,
      cron: parsed.data.cron,
      timezone: parsed.data.timezone,
      disable: parsed.data.disable,
      actorTaskId: parsed.data.actorTaskId,
      actorId: parsed.data.actorId,
      runInput: parsed.data.runInput,
    });
    return NextResponse.json({ job });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message || "Schedule update failed." },
      { status: 500 }
    );
  }
}

