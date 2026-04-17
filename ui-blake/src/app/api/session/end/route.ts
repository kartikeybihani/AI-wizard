import { NextResponse } from "next/server";

import { appendEvent, finalizeSession } from "@/lib/server/session-store";

export const runtime = "nodejs";

type SessionEndRequest = {
  sessionId?: string;
  micWebmBase64?: string;
  assistantWebmBase64?: string;
};

export async function POST(request: Request): Promise<Response> {
  const body = (await request.json().catch(() => ({}))) as SessionEndRequest;

  const sessionId = (body.sessionId || "").trim();
  if (!sessionId) {
    return NextResponse.json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }

  try {
    const meta = finalizeSession(sessionId, {
      micWebmBase64: body.micWebmBase64,
      assistantWebmBase64: body.assistantWebmBase64,
    });

    appendEvent(sessionId, {
      type: "session_finalized",
      hasMicAudio: Boolean(body.micWebmBase64),
      hasAssistantAudio: Boolean(body.assistantWebmBase64),
    });

    return NextResponse.json({ ok: true, meta });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Failed to end session",
      },
      { status: 400 }
    );
  }
}
