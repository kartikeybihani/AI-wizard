import { NextResponse } from "next/server";

import { getRunService } from "@/lib/server";

export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const service = getRunService();
  const payload = service.getResults(id);

  if (!payload) {
    return NextResponse.json({ error: "Run not found." }, { status: 404 });
  }

  return NextResponse.json(payload);
}
