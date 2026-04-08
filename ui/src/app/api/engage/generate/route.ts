import { NextResponse } from "next/server";
import { z } from "zod";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

const generateRequestSchema = z.object({
  limit: z.number().int().min(1).max(100).default(10),
  postIds: z.array(z.string().trim().min(1).max(200)).max(100).optional(),
  whisperModel: z.string().trim().max(120).optional(),
  model: z.string().trim().max(200).optional(),
  force: z.boolean().default(false),
  characterBible: z.string().trim().max(500).optional(),
});

export async function POST(request: Request) {
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const parsed = generateRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid engage generate payload.", issues: parsed.error.flatten() },
      { status: 400 }
    );
  }

  try {
    const service = getMonitorService();
    const job = await service.runGenerate({
      limit: parsed.data.limit,
      postIds: parsed.data.postIds,
      whisperModel: parsed.data.whisperModel,
      model: parsed.data.model,
      force: parsed.data.force,
      characterBible: parsed.data.characterBible,
    });
    return NextResponse.json({ job });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message || "Engage generation failed." },
      { status: 500 }
    );
  }
}
