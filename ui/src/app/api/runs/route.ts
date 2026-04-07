import { NextResponse } from "next/server";

import { getRunService } from "@/lib/server";
import { startRunRequestSchema } from "@/lib/server/presets";

export const runtime = "nodejs";

export async function GET() {
  const service = getRunService();
  const state = service.getDashboardState();
  return NextResponse.json(state);
}

export async function POST(request: Request) {
  const service = getRunService();

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body." },
      { status: 400 }
    );
  }

  const parsed = startRunRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      {
        error: "Invalid run payload.",
        issues: parsed.error.flatten(),
      },
      { status: 400 }
    );
  }

  const run = service.createRun(parsed.data.preset, parsed.data.overrides);
  return NextResponse.json({ run }, { status: 201 });
}
