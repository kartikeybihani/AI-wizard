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
    // Keep session finalization best-effort in serverless environments.
    return NextResponse.json({ ok: true, dropped: true, reason: "missing_session_id" });
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
    const message = error instanceof Error ? error.message : "Failed to end session";
    // Vercel serverless instances do not share local filesystem state.
    // Avoid surfacing this as a hard UI failure when call teardown succeeded.
    return NextResponse.json({ ok: true, dropped: true, reason: message });
  }
}
