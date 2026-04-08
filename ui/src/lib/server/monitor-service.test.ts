import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import Database from "better-sqlite3";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let pipelineCwd = "";

beforeEach(() => {
  pipelineCwd = fs.mkdtempSync(path.join(os.tmpdir(), "toms-monitor-service-"));
});

afterEach(() => {
  delete process.env.PIPELINE_CWD;
  vi.resetModules();
  if (pipelineCwd) {
    fs.rmSync(pipelineCwd, { recursive: true, force: true });
  }
});

async function bootstrapService(): Promise<{
  MonitorService: (new () => {
    submitPost(queueId: number): {
      queueId: number;
      postId: string;
      suggestionId: number;
      finalComment: string;
      username: string;
      url: string;
    };
    rejectSuggestion(suggestionId: number, reason?: string): {
      postId: string;
      queueId: number;
      suggestionId: number;
    };
  });
  dbPath: string;
}> {
  process.env.PIPELINE_CWD = pipelineCwd;
  vi.resetModules();
  const serviceModule = await import("./monitor-service");
  const configModule = await import("./config");
  return {
    MonitorService: serviceModule.MonitorService,
    dbPath: configModule.PIPELINE_MONITOR_DB,
  };
}

function seedQueuePost(dbPath: string, postId: string): number {
  const db = new Database(dbPath);
  try {
    const now = "2026-04-08T00:00:00Z";
    const inserted = db
      .prepare(
        `
        INSERT INTO new_posts_queue (
          post_id, username, caption, url, posted_at, detected_at, status, is_video, media_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        `
      )
      .run(
        postId,
        "mindcharity",
        "caption",
        `https://www.instagram.com/reel/${postId}/`,
        now,
        now,
        "ready_for_review",
        1,
        "reel"
      );
    return Number(inserted.lastInsertRowid);
  } finally {
    db.close();
  }
}

describe("MonitorService engage workflows", () => {
  it("submits directly from pending suggestion and treats it as auto-approved", async () => {
    const { MonitorService, dbPath } = await bootstrapService();
    const service = new MonitorService();
    const queueId = seedQueuePost(dbPath, "POST_DIRECT_SUBMIT");

    const db = new Database(dbPath);
    let highId = 0;
    try {
      const now = "2026-04-08T00:01:00Z";
      db.prepare(
        `
        INSERT INTO comment_suggestions (
          post_id, label, comment, critic_score, decision_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        `
      ).run("POST_DIRECT_SUBMIT", "safe", "Safe comment", 0.2, "pending", now, now);
      const high = db
        .prepare(
          `
          INSERT INTO comment_suggestions (
            post_id, label, comment, critic_score, decision_status, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?)
          `
        )
        .run("POST_DIRECT_SUBMIT", "warm", "Warm comment", 0.9, "pending", now, now);
      highId = Number(high.lastInsertRowid);
    } finally {
      db.close();
    }

    const submitted = service.submitPost(queueId);
    expect(submitted.suggestionId).toBe(highId);
    expect(submitted.finalComment).toBe("Warm comment");

    const verifyDb = new Database(dbPath, { readonly: true });
    try {
      const chosen = verifyDb
        .prepare(
          `
          SELECT decision_status, decision_reason, final_comment, submitted_at, decision_at
          FROM comment_suggestions
          WHERE id = ?
          `
        )
        .get(highId) as
        | {
            decision_status: string;
            decision_reason: string | null;
            final_comment: string | null;
            submitted_at: string | null;
            decision_at: string | null;
          }
        | undefined;
      expect(chosen?.decision_status).toBe("submitted");
      expect(chosen?.decision_reason).toBe("Auto-approved via submit.");
      expect(chosen?.final_comment).toBe("Warm comment");
      expect(chosen?.submitted_at).toBeTruthy();
      expect(chosen?.decision_at).toBeTruthy();

      const queueRow = verifyDb
        .prepare(`SELECT status FROM new_posts_queue WHERE id = ?`)
        .get(queueId) as { status: string } | undefined;
      expect(queueRow?.status).toBe("submitted");

      const processingRow = verifyDb
        .prepare(`SELECT status, selected_suggestion_id FROM post_processing WHERE post_id = ?`)
        .get("POST_DIRECT_SUBMIT") as
        | { status: string; selected_suggestion_id: number | null }
        | undefined;
      expect(processingRow?.status).toBe("submitted");
      expect(processingRow?.selected_suggestion_id).toBe(highId);
    } finally {
      verifyDb.close();
    }
  });

  it("keeps post reviewable when one suggestion is rejected and rejects only when all are rejected", async () => {
    const { MonitorService, dbPath } = await bootstrapService();
    const service = new MonitorService();
    const queueId = seedQueuePost(dbPath, "POST_REJECTION_FLOW");

    const db = new Database(dbPath);
    let suggestionA = 0;
    let suggestionB = 0;
    try {
      const now = "2026-04-08T00:02:00Z";
      suggestionA = Number(
        db
          .prepare(
            `
            INSERT INTO comment_suggestions (
              post_id, label, comment, decision_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            `
          )
          .run("POST_REJECTION_FLOW", "a", "Comment A", "pending", now, now).lastInsertRowid
      );
      suggestionB = Number(
        db
          .prepare(
            `
            INSERT INTO comment_suggestions (
              post_id, label, comment, decision_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            `
          )
          .run("POST_REJECTION_FLOW", "b", "Comment B", "pending", now, now).lastInsertRowid
      );
    } finally {
      db.close();
    }

    service.rejectSuggestion(suggestionA, "too generic");

    const midDb = new Database(dbPath, { readonly: true });
    try {
      const queueMid = midDb
        .prepare(`SELECT status FROM new_posts_queue WHERE id = ?`)
        .get(queueId) as { status: string } | undefined;
      expect(queueMid?.status).toBe("ready_for_review");

      const processingMid = midDb
        .prepare(`SELECT status, selected_suggestion_id FROM post_processing WHERE post_id = ?`)
        .get("POST_REJECTION_FLOW") as
        | { status: string; selected_suggestion_id: number | null }
        | undefined;
      expect(processingMid?.status).toBe("ready_for_review");
      expect(processingMid?.selected_suggestion_id).toBeNull();
    } finally {
      midDb.close();
    }

    service.rejectSuggestion(suggestionB, "off-brand");

    const finalDb = new Database(dbPath, { readonly: true });
    try {
      const queueFinal = finalDb
        .prepare(`SELECT status FROM new_posts_queue WHERE id = ?`)
        .get(queueId) as { status: string } | undefined;
      expect(queueFinal?.status).toBe("rejected");

      const processingFinal = finalDb
        .prepare(`SELECT status, error_message FROM post_processing WHERE post_id = ?`)
        .get("POST_REJECTION_FLOW") as { status: string; error_message: string | null } | undefined;
      expect(processingFinal?.status).toBe("rejected");
      expect(processingFinal?.error_message).toBe("off-brand");
    } finally {
      finalDb.close();
    }
  });
});
