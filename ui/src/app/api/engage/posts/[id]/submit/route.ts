import { NextResponse } from "next/server";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const queueId = Number(id);
  if (!Number.isFinite(queueId) || queueId <= 0) {
    return NextResponse.json({ error: "Invalid post queue id." }, { status: 400 });
  }

  try {
    const service = getMonitorService();
    const result = service.submitPost(queueId);
    return NextResponse.json({ result });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message || "Failed to submit post comment." },
      { status: 500 }
    );
  }
}
