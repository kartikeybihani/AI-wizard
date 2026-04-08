import { NextResponse } from "next/server";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const service = getMonitorService();
  const job = service.getJob(id);

  if (!job) {
    return NextResponse.json({ error: "Monitor job not found." }, { status: 404 });
  }

  return NextResponse.json({ job });
}

