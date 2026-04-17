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
    return NextResponse.json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }

  const eventType = (body.eventType || "event").trim();

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
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Failed to append event",
      },
      { status: 400 }
    );
  }
}
