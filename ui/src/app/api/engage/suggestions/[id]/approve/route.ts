import { NextResponse } from "next/server";
import { z } from "zod";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

const approveSchema = z.object({
  editedText: z.string().trim().max(5000).optional(),
});

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const suggestionId = Number(id);
  if (!Number.isFinite(suggestionId) || suggestionId <= 0) {
    return NextResponse.json({ error: "Invalid suggestion id." }, { status: 400 });
  }

  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const parsed = approveSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid approve payload.", issues: parsed.error.flatten() },
      { status: 400 }
    );
  }

  try {
    const service = getMonitorService();
    const result = service.approveSuggestion(suggestionId, parsed.data.editedText);
    return NextResponse.json({ result });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message || "Failed to approve suggestion." },
      { status: 500 }
    );
  }
}
