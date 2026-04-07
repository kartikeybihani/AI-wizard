import { NextResponse } from "next/server";

import { getRunService } from "@/lib/server";

export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const service = getRunService();
  const run = service.getRun(id);

  if (!run) {
    return NextResponse.json({ error: "Run not found." }, { status: 404 });
  }

  const logs = service.getLogTail(id, 400);
  return NextResponse.json({ run, logs });
}
