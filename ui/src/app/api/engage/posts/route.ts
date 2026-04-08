import { NextResponse } from "next/server";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const statusParam = searchParams.get("status");
  const status = statusParam === "all" ? "" : statusParam ?? "ready_for_review";
  const limitRaw = Number(searchParams.get("limit") || 10);
  const limit = Number.isFinite(limitRaw) ? Math.max(1, Math.min(100, Math.floor(limitRaw))) : 10;

  try {
    const service = getMonitorService();
    const posts = service.getEngagePosts({ status, limit });
    const statusCounts = service.getEngageStatusCounts();
    return NextResponse.json({ posts, statusCounts });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message || "Failed to load engage posts." },
      { status: 500 }
    );
  }
}
