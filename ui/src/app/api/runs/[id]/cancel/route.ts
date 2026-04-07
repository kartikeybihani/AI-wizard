import { NextResponse } from "next/server";

import { getRunService } from "@/lib/server";

export const runtime = "nodejs";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const service = getRunService();
  const run = await service.cancelRun(id);

  if (!run) {
    return NextResponse.json({ error: "Run not found." }, { status: 404 });
  }

  return NextResponse.json({ run });
}
