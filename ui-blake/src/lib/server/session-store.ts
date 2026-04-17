import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";

import { SESSION_DIR, ensureServerDirectories } from "@/lib/server/config";

export interface TranscriptTurn {
  id: string;
  speaker: "user" | "assistant";
  text: string;
  ts: string;
}

export interface SessionMeta {
  sessionId: string;
  status: "active" | "ended";
  startedAt: string;
  endedAt?: string;
  updatedAt: string;
}

function nowIso(): string {
  return new Date().toISOString();
}

function safeReadJson<T>(filepath: string, fallback: T): T {
  if (!fs.existsSync(filepath)) {
    return fallback;
  }
  try {
    return JSON.parse(fs.readFileSync(filepath, "utf-8")) as T;
  } catch {
    return fallback;
  }
}

function sessionPath(sessionId: string): string {
  return path.join(SESSION_DIR, sessionId);
}

function filePaths(sessionId: string): {
  dir: string;
  meta: string;
  transcript: string;
  events: string;
  micAudio: string;
  assistantAudio: string;
} {
  const dir = sessionPath(sessionId);
  return {
    dir,
    meta: path.join(dir, "meta.json"),
    transcript: path.join(dir, "transcript.json"),
    events: path.join(dir, "events.jsonl"),
    micAudio: path.join(dir, "mic.webm"),
    assistantAudio: path.join(dir, "assistant.webm"),
  };
}

export function startSession(): SessionMeta {
  ensureServerDirectories();

  const sessionId = randomUUID();
  const paths = filePaths(sessionId);
  fs.mkdirSync(paths.dir, { recursive: true });

  const meta: SessionMeta = {
    sessionId,
    status: "active",
    startedAt: nowIso(),
    updatedAt: nowIso(),
  };

  fs.writeFileSync(paths.meta, JSON.stringify(meta, null, 2));
  fs.writeFileSync(paths.transcript, JSON.stringify([], null, 2));
  fs.writeFileSync(paths.events, "");

  return meta;
}

export function appendEvent(sessionId: string, event: Record<string, unknown>): void {
  const paths = filePaths(sessionId);
  if (!fs.existsSync(paths.dir)) {
    throw new Error(`Unknown session id: ${sessionId}`);
  }

  const line = JSON.stringify({ ts: nowIso(), ...event });
  fs.appendFileSync(paths.events, `${line}\n`);

  const meta = safeReadJson<SessionMeta | null>(paths.meta, null);
  if (meta) {
    meta.updatedAt = nowIso();
    fs.writeFileSync(paths.meta, JSON.stringify(meta, null, 2));
  }
}

export function upsertTranscriptTurn(sessionId: string, turn: TranscriptTurn): void {
  const paths = filePaths(sessionId);
  const current = safeReadJson<TranscriptTurn[]>(paths.transcript, []);

  const next = [...current, turn];
  fs.writeFileSync(paths.transcript, JSON.stringify(next, null, 2));
}

function decodeBase64(input: string): Buffer {
  const cleaned = input.includes(",") ? input.slice(input.indexOf(",") + 1) : input;
  return Buffer.from(cleaned, "base64");
}

export function finalizeSession(
  sessionId: string,
  payload: {
    micWebmBase64?: string;
    assistantWebmBase64?: string;
  }
): SessionMeta {
  const paths = filePaths(sessionId);
  if (!fs.existsSync(paths.dir)) {
    throw new Error(`Unknown session id: ${sessionId}`);
  }

  if (payload.micWebmBase64) {
    fs.writeFileSync(paths.micAudio, decodeBase64(payload.micWebmBase64));
  }
  if (payload.assistantWebmBase64) {
    fs.writeFileSync(paths.assistantAudio, decodeBase64(payload.assistantWebmBase64));
  }

  const meta = safeReadJson<SessionMeta | null>(paths.meta, null);
  if (!meta) {
    throw new Error("Missing session meta");
  }

  meta.status = "ended";
  meta.endedAt = nowIso();
  meta.updatedAt = nowIso();
  fs.writeFileSync(paths.meta, JSON.stringify(meta, null, 2));
  return meta;
}

export function exportSession(sessionId: string): {
  meta: SessionMeta;
  transcript: TranscriptTurn[];
  events: Array<Record<string, unknown>>;
  files: {
    micWebm: boolean;
    assistantWebm: boolean;
  };
} {
  const paths = filePaths(sessionId);
  if (!fs.existsSync(paths.dir)) {
    throw new Error(`Unknown session id: ${sessionId}`);
  }

  const meta = safeReadJson<SessionMeta | null>(paths.meta, null);
  if (!meta) {
    throw new Error("Missing meta file");
  }

  const transcript = safeReadJson<TranscriptTurn[]>(paths.transcript, []);

  const rawEvents = fs.existsSync(paths.events) ? fs.readFileSync(paths.events, "utf-8") : "";
  const events = rawEvents
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line) as Record<string, unknown>;
      } catch {
        return { type: "parse_error", raw: line };
      }
    });

  return {
    meta,
    transcript,
    events,
    files: {
      micWebm: fs.existsSync(paths.micAudio),
      assistantWebm: fs.existsSync(paths.assistantAudio),
    },
  };
}
