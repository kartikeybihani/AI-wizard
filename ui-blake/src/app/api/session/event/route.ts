import { randomUUID } from "node:crypto";

import { NextResponse } from "next/server";

import { appendEvent, upsertTranscriptTurn } from "@/lib/server/session-store";

export const runtime = "nodejs";

type SessionEventRequest = {
  sessionId?: string;
  eventType?: string;
  data?: Record<string, unknown>;
  transcriptTurn?: {
    speaker?: "user" | "assistant";
    text?: string;
    ts?: string;
  };
};

export async function POST(request: Request): Promise<Response> {
  const body = (await request.json().catch(() => ({}))) as SessionEventRequest;

  const sessionId = (body.sessionId || "").trim();
  if (!sessionId) {
    // Telemetry events are best-effort; do not surface as hard errors.
    return NextResponse.json({ ok: true, dropped: true, reason: "missing_session_id" });
  }

  const eventType = (body.eventType || "event").trim();
  console.log("[ui-blake] session_event", {
    sessionId: sessionId.slice(0, 8),
    eventType,
    hasTurn: Boolean(body.transcriptTurn),
  });

  try {
    appendEvent(sessionId, {
      type: eventType,
      ...(body.data || {}),
    });

    const turn = body.transcriptTurn;
    if (turn?.speaker && turn.text && turn.text.trim()) {
      upsertTranscriptTurn(sessionId, {
        id: randomUUID(),
        speaker: turn.speaker,
        text: turn.text.trim(),
        ts: turn.ts || new Date().toISOString(),
      });
    }

    return NextResponse.json({ ok: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to append event";
    // Vercel serverless instances may not share local filesystem state.
    // Keep event ingestion non-blocking and avoid noisy 4xx logs.
    return NextResponse.json({ ok: true, dropped: true, reason: message });
  }
}
