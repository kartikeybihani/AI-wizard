"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type TranscriptTurn = {
  id: string;
  speaker: "user" | "assistant";
  text: string;
  ts: string;
};

type SessionStartResponse = {
  ok: boolean;
  sessionId: string;
};

type SignedUrlResponse = {
  signedUrl: string;
  conversationId: string | null;
  voiceId: string | null;
};

type ExportPayload = {
  ok: boolean;
  meta?: Record<string, unknown>;
  transcript?: Array<Record<string, unknown>>;
  events?: Array<Record<string, unknown>>;
  files?: Record<string, boolean>;
  error?: string;
};

type ConversationHandle = {
  endSession: () => Promise<void>;
  setMicMuted: (muted: boolean) => void;
  getId: () => string;
  input?: {
    inputStream?: MediaStream;
  };
  output?: {
    context?: AudioContext;
    gain?: GainNode;
  };
};

const RECORDER_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm"];

function stringifyUnknown(value: unknown): string {
  if (value instanceof Error) {
    return value.message;
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function formatSdkError(value: unknown): string {
  if (value instanceof Error) {
    return value.message || "SDK error";
  }
  if (typeof value === "string") {
    return value;
  }
  if (value && typeof value === "object") {
    const rec = value as Record<string, unknown>;
    const errEvent = rec as {
      message?: unknown;
      type?: unknown;
      isTrusted?: unknown;
      error?: unknown;
      reason?: unknown;
      code?: unknown;
    };
    const fromMessage = typeof errEvent.message === "string" && errEvent.message.trim() ? errEvent.message.trim() : "";
    if (fromMessage) {
      return fromMessage;
    }
    const fromReason = typeof errEvent.reason === "string" && errEvent.reason.trim() ? errEvent.reason.trim() : "";
    if (fromReason) {
      return fromReason;
    }
    const type = typeof errEvent.type === "string" ? errEvent.type : "unknown";
    const code = typeof errEvent.code === "number" ? ` code=${String(errEvent.code)}` : "";
    return `SDK event error (${type})${code}`;
  }
  return stringifyUnknown(value);
}

function nowIso(): string {
  return new Date().toISOString();
}

function createTurnId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `turn_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function supportedRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") {
    return undefined;
  }
  for (const mime of RECORDER_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(mime)) {
      return mime;
    }
  }
  return undefined;
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const value = reader.result;
      if (typeof value !== "string") {
        reject(new Error("Failed to convert audio blob to base64"));
        return;
      }
      const comma = value.indexOf(",");
      resolve(comma >= 0 ? value.slice(comma + 1) : value);
    };
    reader.onerror = () => reject(new Error("FileReader failed"));
    reader.readAsDataURL(blob);
  });
}

function stopRecorder(recorder: MediaRecorder | null, chunks: Blob[]): Promise<Blob | null> {
  if (!recorder) {
    return Promise.resolve(null);
  }

  if (recorder.state === "inactive") {
    return Promise.resolve(chunks.length ? new Blob(chunks, { type: recorder.mimeType || "audio/webm" }) : null);
  }

  return new Promise((resolve) => {
    recorder.addEventListener(
      "stop",
      () => {
        if (!chunks.length) {
          resolve(null);
          return;
        }
        resolve(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      },
      { once: true }
    );
    recorder.stop();
  });
}

export default function HomePage() {
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnecting" | "disconnected">("disconnected");
  const [mode, setMode] = useState<"speaking" | "listening" | "idle">("idle");
  const [sessionId, setSessionId] = useState<string>("");
  const [conversationId, setConversationId] = useState<string>("");
  const [micMuted, setMicMuted] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [isBusy, setIsBusy] = useState<boolean>(false);
  const [isStopping, setIsStopping] = useState<boolean>(false);
  const [exportPreview, setExportPreview] = useState<string>("");

  const conversationRef = useRef<ConversationHandle | null>(null);
  const sessionIdRef = useRef<string>("");
  const modeRef = useRef<"speaking" | "listening" | "idle">("idle");

  const micRecorderRef = useRef<MediaRecorder | null>(null);
  const assistantRecorderRef = useRef<MediaRecorder | null>(null);
  const micChunksRef = useRef<Blob[]>([]);
  const assistantChunksRef = useRef<Blob[]>([]);
  const assistantTapDestinationRef = useRef<MediaStreamAudioDestinationNode | null>(null);

  const callApi = useCallback(async <T,>(url: string, init?: RequestInit): Promise<T> => {
    const response = await fetch(url, init);
    const text = await response.text();
    let payload: Record<string, unknown> = {};
    if (text) {
      try {
        payload = JSON.parse(text) as Record<string, unknown>;
      } catch {
        payload = { raw: text };
      }
    }
    if (!response.ok) {
      const apiError = typeof payload.error === "string" ? payload.error : "";
      const apiMessage = typeof payload.message === "string" ? payload.message : "";
      const detail = payload.details ? ` | details=${stringifyUnknown(payload.details)}` : "";
      const reason = apiError || apiMessage || `Request failed (${response.status}) for ${url}`;
      throw new Error(`${reason}${detail}`);
    }
    if (payload && payload.ok === false) {
      const apiError = typeof payload.error === "string" ? payload.error : "";
      throw new Error(apiError || `API returned ok=false for ${url}`);
    }
    return payload as T;
  }, []);

  const pushEvent = useCallback(
    async (eventType: string, data?: Record<string, unknown>, turn?: Omit<TranscriptTurn, "id">) => {
      const sid = sessionIdRef.current;
      if (!sid) {
        return;
      }
      const body: Record<string, unknown> = {
        sessionId: sid,
        eventType,
        data: data || {},
      };
      if (turn) {
        body.transcriptTurn = {
          speaker: turn.speaker,
          text: turn.text,
          ts: turn.ts,
        };
      }
      try {
        await fetch("/api/session/event", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } catch {
        // Keep realtime flow resilient; dropped telemetry should not break session.
      }
    },
    []
  );

  const startRecorder = useCallback((stream: MediaStream, onChunk: (chunk: Blob) => void): MediaRecorder | null => {
    if (typeof MediaRecorder === "undefined") {
      return null;
    }
    try {
      const mimeType = supportedRecorderMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          onChunk(event.data);
        }
      });
      recorder.start(1000);
      return recorder;
    } catch {
      return null;
    }
  }, []);

  const appendTurn = useCallback(
    (speaker: "user" | "assistant", text: string) => {
      const trimmed = text.trim();
      if (!trimmed) {
        return;
      }

      const ts = nowIso();
      setTranscript((current) => {
        const last = current[current.length - 1];
        if (last && last.speaker === speaker && last.text.trim() === trimmed) {
          return current;
        }
        const nextTurn: TranscriptTurn = {
          id: createTurnId(),
          speaker,
          text: trimmed,
          ts,
        };
        void pushEvent(
          "transcript",
          { speaker, text: trimmed },
          {
            speaker,
            text: trimmed,
            ts,
          }
        );
        return [...current, nextTurn];
      });

      if (speaker === "user" && modeRef.current === "speaking") {
        void pushEvent("interruption", {
          reason: "user_barge_in_inferred",
        });
      }
    },
    [pushEvent]
  );

  const startSession = useCallback(async () => {
    if (conversationRef.current || isBusy) {
      return;
    }

    setError("");
    setIsBusy(true);
    setTranscript([]);
    setExportPreview("");
    setMicMuted(false);

    micChunksRef.current = [];
    assistantChunksRef.current = [];

    try {
      const session = await callApi<SessionStartResponse>("/api/session/start", {
        method: "POST",
      });
      sessionIdRef.current = session.sessionId;
      setSessionId(session.sessionId);

      await pushEvent("session_started", {
        ui: "ui-blake",
      });

      const signed = await callApi<SignedUrlResponse>("/api/eleven/signed-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ includeConversationId: true }),
      });

      const sdk = await import("@elevenlabs/client");

      const conversation = (await sdk.Conversation.startSession({
        signedUrl: signed.signedUrl,
        connectionType: "websocket",
        // Keep websocket bootstrap minimal for reliability on hosted environments.
        // We can add dynamic variables/overrides back after stable connection is confirmed.
        onConnect: ({ conversationId: cid }: { conversationId: string }) => {
          setConversationId(cid);
          void pushEvent("eleven_connected", {
            conversationId: cid,
          });
        },
        onStatusChange: ({ status: nextStatus }: { status: "connecting" | "connected" | "disconnecting" | "disconnected" }) => {
          setStatus(nextStatus);
          void pushEvent("status", { status: nextStatus });
        },
        onModeChange: ({ mode: nextMode }: { mode: "speaking" | "listening" }) => {
          modeRef.current = nextMode;
          setMode(nextMode);
          void pushEvent("mode", { mode: nextMode });
        },
        onMessage: ({ source, message }: { source: "user" | "ai"; message: string }) => {
          appendTurn(source === "ai" ? "assistant" : "user", message);
        },
        onError: (raw: unknown) => {
          const message = formatSdkError(raw);
          setError(message);
          console.error("[ui-blake] eleven sdk error", raw);
          void pushEvent("sdk_error", { message, raw: stringifyUnknown(raw) });
        },
        onDisconnect: (details: unknown) => {
          setStatus("disconnected");
          modeRef.current = "idle";
          setMode("idle");
          void pushEvent("eleven_disconnected", {
            details: typeof details === "object" && details ? details : { reason: "unknown" },
          });
        },
      })) as unknown as ConversationHandle;

      conversationRef.current = conversation;
      setConversationId(conversation.getId?.() || signed.conversationId || "");

      if (conversation.input?.inputStream) {
        micRecorderRef.current = startRecorder(conversation.input.inputStream, (chunk) => {
          micChunksRef.current.push(chunk);
        });
      }

      const outputGain = conversation.output?.gain;
      const outputContext = conversation.output?.context;
      if (outputGain && outputContext) {
        const tapDestination = outputContext.createMediaStreamDestination();
        outputGain.connect(tapDestination);
        assistantTapDestinationRef.current = tapDestination;

        assistantRecorderRef.current = startRecorder(tapDestination.stream, (chunk) => {
          assistantChunksRef.current.push(chunk);
        });
      }

      await pushEvent("recording_started", {
        micRecorder: Boolean(micRecorderRef.current),
        assistantRecorder: Boolean(assistantRecorderRef.current),
      });
    } catch (err) {
      const message = stringifyUnknown(err) || "Failed to start session";
      setError(message);
      void pushEvent("session_start_error", {
        message,
      });
      setStatus("disconnected");
      modeRef.current = "idle";
      setMode("idle");
    } finally {
      setIsBusy(false);
    }
  }, [appendTurn, callApi, isBusy, pushEvent, startRecorder]);

  const stopSession = useCallback(async () => {
    if (!sessionIdRef.current || isStopping) {
      return;
    }
    setIsStopping(true);

    const convo = conversationRef.current;
    conversationRef.current = null;

    try {
      setStatus("disconnecting");
      if (convo) {
        await convo.endSession();
      }

      const [micBlob, assistantBlob] = await Promise.all([
        stopRecorder(micRecorderRef.current, micChunksRef.current),
        stopRecorder(assistantRecorderRef.current, assistantChunksRef.current),
      ]);

      micRecorderRef.current = null;
      assistantRecorderRef.current = null;

      const tap = assistantTapDestinationRef.current;
      if (tap) {
        const tracks = tap.stream.getTracks();
        for (const track of tracks) {
          track.stop();
        }
      }
      assistantTapDestinationRef.current = null;

      const micBase64 = micBlob ? await blobToBase64(micBlob) : undefined;
      const assistantBase64 = assistantBlob ? await blobToBase64(assistantBlob) : undefined;

      await callApi<{ ok: boolean }>("/api/session/end", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: sessionIdRef.current,
          micWebmBase64: micBase64,
          assistantWebmBase64: assistantBase64,
        }),
      });

      await pushEvent("session_stopped", {
        savedMicAudio: Boolean(micBase64),
        savedAssistantAudio: Boolean(assistantBase64),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop session");
    } finally {
      setStatus("disconnected");
      modeRef.current = "idle";
      setMode("idle");
      setIsStopping(false);
    }
  }, [callApi, isStopping, pushEvent]);

  const toggleMic = useCallback(() => {
    const convo = conversationRef.current;
    if (!convo) {
      return;
    }
    const nextMuted = !micMuted;
    convo.setMicMuted(nextMuted);
    setMicMuted(nextMuted);
    void pushEvent("mic_toggle", { muted: nextMuted });
  }, [micMuted, pushEvent]);

  const loadExport = useCallback(async () => {
    if (!sessionIdRef.current) {
      return;
    }
    try {
      const payload = await callApi<ExportPayload>(`/api/session/export?id=${encodeURIComponent(sessionIdRef.current)}`);
      setExportPreview(JSON.stringify(payload, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }, [callApi]);

  const downloadExport = useCallback(async () => {
    if (!sessionIdRef.current) {
      return;
    }
    try {
      const payload = await callApi<ExportPayload>(`/api/session/export?id=${encodeURIComponent(sessionIdRef.current)}`);
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${sessionIdRef.current}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export download failed");
    }
  }, [callApi]);

  useEffect(() => {
    return () => {
      const convo = conversationRef.current;
      if (convo) {
        void convo.endSession();
      }
    };
  }, []);

  const canStart = useMemo(() => !conversationRef.current && !isBusy && status !== "connecting", [isBusy, status]);
  const canStop = useMemo(() => Boolean(sessionIdRef.current) && !isStopping, [isStopping]);

  return (
    <main className="page">
      <section className="panel">
        <h1>Blake AI Interview v1</h1>
        <p className="sub">Minimal realtime voice interview test app.</p>

        <div className="controls">
          <button onClick={() => void startSession()} disabled={!canStart}>
            {status === "connected" || status === "connecting" ? "Connected" : "Connect"}
          </button>
          <button onClick={() => void stopSession()} disabled={!canStop}>
            Disconnect
          </button>
          <button onClick={toggleMic} disabled={!conversationRef.current}>
            {micMuted ? "Unmute Mic" : "Mute Mic"}
          </button>
        </div>

        <div className="meta-grid">
          <div>
            <span>Status</span>
            <strong>{status}</strong>
          </div>
          <div>
            <span>Mode</span>
            <strong>{mode}</strong>
          </div>
          <div>
            <span>Session</span>
            <strong>{sessionId || "-"}</strong>
          </div>
          <div>
            <span>Conversation</span>
            <strong>{conversationId || "-"}</strong>
          </div>
        </div>

        {error ? <p className="error">{error}</p> : null}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>Live Transcript</h2>
          <span>{transcript.length} turns</span>
        </div>

        <div className="transcript">
          {transcript.length === 0 ? <p className="empty">No transcript yet.</p> : null}
          {transcript.map((turn) => (
            <article key={turn.id} className={`turn ${turn.speaker}`}>
              <header>
                <strong>{turn.speaker === "assistant" ? "AI Blake" : "Blake"}</strong>
                <time>{new Date(turn.ts).toLocaleTimeString()}</time>
              </header>
              <p>{turn.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>Export</h2>
        </div>
        <div className="controls">
          <button onClick={() => void loadExport()} disabled={!sessionId}>
            Load Export JSON
          </button>
          <button onClick={() => void downloadExport()} disabled={!sessionId}>
            Download Export JSON
          </button>
        </div>
        <pre className="export">{exportPreview || "No export loaded."}</pre>
      </section>
    </main>
  );
}
