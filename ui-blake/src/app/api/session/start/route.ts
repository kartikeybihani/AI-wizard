import { NextResponse } from "next/server";

import { startSession } from "@/lib/server/session-store";

export const runtime = "nodejs";

export async function POST(): Promise<Response> {
  try {
    const meta = startSession();
    return NextResponse.json({ ok: true, sessionId: meta.sessionId, meta });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Failed to start session",
      },
      { status: 500 }
    );
  }
}
