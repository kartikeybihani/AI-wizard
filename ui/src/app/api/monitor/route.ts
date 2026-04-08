import { NextResponse } from "next/server";

import { getMonitorService } from "@/lib/server";

export const runtime = "nodejs";

export async function GET() {
  const service = getMonitorService();
  const overview = service.getOverview();
  return NextResponse.json(overview);
}

