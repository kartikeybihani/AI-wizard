import fs from "node:fs";
import path from "node:path";

import { NextResponse } from "next/server";

import type { ArtifactPaths } from "@/lib/types";
import { getRunService } from "@/lib/server";

export const runtime = "nodejs";

const ALLOWED_FILES: Record<string, keyof ArtifactPaths> = {
  raw_handles: "rawHandles",
  enriched: "enriched",
  scored: "scored",
  final_ranked: "finalRanked",
  review_bucket: "reviewBucket",
  run_log: "runLog",
};

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const url = new URL(request.url);
  const file = url.searchParams.get("file") || "final_ranked";

  const artifactKey = ALLOWED_FILES[file];
  if (!artifactKey) {
    return NextResponse.json(
      {
        error: "Invalid file parameter.",
      },
      { status: 400 }
    );
  }

  const service = getRunService();
  const filePath = service.getDownloadPath(id, artifactKey);
  if (!filePath) {
    return NextResponse.json({ error: "Artifact not found." }, { status: 404 });
  }

  const filename = path.basename(filePath);
  const isJson = filename.endsWith(".json");
  const isLog = filename.endsWith(".log");

  const body = fs.readFileSync(filePath);

  return new NextResponse(body, {
    headers: {
      "Content-Type": isJson
        ? "application/json"
        : isLog
          ? "text/plain"
          : "text/csv",
      "Content-Disposition": `attachment; filename=\"${filename}\"`,
    },
  });
}
