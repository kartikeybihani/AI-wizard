import { NextResponse } from "next/server";

import { exportSession } from "@/lib/server/session-store";

export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const sessionId = (searchParams.get("id") || "").trim();

  if (!sessionId) {
    return NextResponse.json({ ok: false, error: "Missing id query param" }, { status: 400 });
  }

  try {
    const data = exportSession(sessionId);
    return NextResponse.json({ ok: true, ...data }, { status: 200 });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Failed to export session",
      },
      { status: 404 }
    );
  }
}
