import { NextResponse } from "next/server";

import {
  ELEVENLABS_AGENT_ID,
  ELEVENLABS_API_KEY,
  ELEVENLABS_BASE_URL,
  ELEVENLABS_BRANCH_ID,
  ELEVENLABS_VOICE_ID,
} from "@/lib/server/config";

export const runtime = "nodejs";

type SignedUrlRequest = {
  agentId?: string;
  includeConversationId?: boolean;
  branchId?: string;
};

export async function POST(request: Request): Promise<Response> {
  const body = (await request.json().catch(() => ({}))) as SignedUrlRequest;

  const agentId = (body.agentId || ELEVENLABS_AGENT_ID || "").trim();
  if (!agentId) {
    return NextResponse.json(
      { error: "Missing agent id. Set ELEVENLABS_AGENT_ID or pass agentId." },
      { status: 400 }
    );
  }

  if (!ELEVENLABS_API_KEY) {
    return NextResponse.json(
      { error: "Missing ELEVENLABS_API_KEY in server environment." },
      { status: 500 }
    );
  }

  const includeConversationId = body.includeConversationId ?? true;

  const params = new URLSearchParams();
  params.set("agent_id", agentId);
  if (includeConversationId) {
    params.set("include_conversation_id", "true");
  }
  const branchId = (body.branchId || ELEVENLABS_BRANCH_ID || "").trim();
  if (branchId) {
    params.set("branch_id", branchId);
  }

  const url = `${ELEVENLABS_BASE_URL.replace(/\/$/, "")}/v1/convai/conversation/get-signed-url?${params.toString()}`;

  const upstream = await fetch(url, {
    method: "GET",
    headers: {
      "xi-api-key": ELEVENLABS_API_KEY,
      Accept: "application/json",
    },
    cache: "no-store",
  });

  const text = await upstream.text();
  let payload: Record<string, unknown> = {};
  if (text) {
    try {
      payload = JSON.parse(text) as Record<string, unknown>;
    } catch {
      payload = { raw: text };
    }
  }

  if (!upstream.ok) {
    console.error("[ui-blake] eleven signed-url upstream error", {
      status: upstream.status,
      payload,
    });
    return NextResponse.json(
      {
        error: "Failed to fetch Eleven signed URL.",
        status: upstream.status,
        details: payload,
      },
      { status: 502 }
    );
  }

  const signedUrl = String(payload.signed_url || "");
  if (!signedUrl) {
    console.error("[ui-blake] eleven signed-url missing field", { payload });
    return NextResponse.json(
      {
        error: "Eleven signed URL response missing signed_url.",
        details: payload,
      },
      { status: 502 }
    );
  }

  return NextResponse.json(
    {
      signedUrl,
      conversationId: payload.conversation_id ? String(payload.conversation_id) : null,
      agentId,
      voiceId: ELEVENLABS_VOICE_ID || null,
    },
    { status: 200 }
  );
}
