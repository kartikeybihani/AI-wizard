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

type UiStatus = "connecting" | "connected" | "disconnecting" | "disconnected";
type UiMode = "speaking" | "listening" | "idle";

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
    const msg = typeof rec.message === "string" ? rec.message.trim() : "";
    const reason = typeof rec.reason === "string" ? rec.reason.trim() : "";
    if (msg) {
      return msg;
    }
    if (reason) {
      return reason;
    }
    return `SDK event error (${String(rec.type || "unknown")})`;
  }
  return stringifyUnknown(value);
}

function nowIso(): string {
  return new Date().toISOString();
}

function createTurnId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
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

function stopRecorder(
  recorder: MediaRecorder | null,
  chunks: Blob[],
): Promise<Blob | null> {
  if (!recorder) {
    return Promise.resolve(null);
  }

  if (recorder.state === "inactive") {
    return Promise.resolve(
      chunks.length
        ? new Blob(chunks, { type: recorder.mimeType || "audio/webm" })
        : null,
    );
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
      { once: true },
    );
    recorder.stop();
  });
}

function isPlaceholderUserUtterance(text: string): boolean {
  const value = text.trim();
  return value === "..." || value === "…" || value === ".";
}

function PhoneIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M6.62 10.79a15.5 15.5 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.01-.24c1.11.37 2.31.56 3.58.56a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.85 21 3 13.15 3 3a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.27.19 2.47.56 3.58a1 1 0 0 1-.24 1.01l-2.2 2.2z"
        fill="currentColor"
      />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zm5-3a1 1 0 1 1 2 0 7 7 0 0 1-6 6.92V21h3a1 1 0 1 1 0 2H8a1 1 0 0 1 0-2h3v-2.08A7 7 0 0 1 5 12a1 1 0 1 1 2 0 5 5 0 0 0 10 0z"
        fill="currentColor"
      />
    </svg>
  );
}

function MicOffIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M18.89 16.48A6.97 6.97 0 0 0 19 12a1 1 0 1 0-2 0 5 5 0 0 1-.38 1.91L15 12.29V6a3 3 0 0 0-5.27-1.96 1 1 0 0 0 1.54 1.28A1 1 0 0 1 13 6v4.29L4.71 2.01a1 1 0 1 0-1.42 1.41l14 14a1 1 0 0 0 1.42-1.41zM5 12a1 1 0 1 1 2 0 5 5 0 0 0 6.53 4.76l1.62 1.62A6.93 6.93 0 0 1 13 18.92V21h3a1 1 0 1 1 0 2H8a1 1 0 0 1 0-2h3v-2.08A7 7 0 0 1 5 12z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function HomePage() {
  const [status, setStatus] = useState<UiStatus>("disconnected");
  const [mode, setMode] = useState<UiMode>("idle");
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
  const modeRef = useRef<UiMode>("idle");
  const micMutedRef = useRef<boolean>(false);

  const micRecorderRef = useRef<MediaRecorder | null>(null);
  const assistantRecorderRef = useRef<MediaRecorder | null>(null);
  const micChunksRef = useRef<Blob[]>([]);
  const assistantChunksRef = useRef<Blob[]>([]);
  const assistantTapDestinationRef =
    useRef<MediaStreamAudioDestinationNode | null>(null);

  const callApi = useCallback(
    async <T,>(url: string, init?: RequestInit): Promise<T> => {
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
        const apiMessage =
          typeof payload.message === "string" ? payload.message : "";
        const details = payload.details
          ? ` | details=${stringifyUnknown(payload.details)}`
          : "";
        const reason =
          apiError ||
          apiMessage ||
          `Request failed (${response.status}) for ${url}`;
        throw new Error(`${reason}${details}`);
      }
      if (payload.ok === false) {
        const apiError = typeof payload.error === "string" ? payload.error : "";
        throw new Error(apiError || `API returned ok=false for ${url}`);
      }
      return payload as T;
    },
    [],
  );

  const pushEvent = useCallback(
    async (
      eventType: string,
      data?: Record<string, unknown>,
      turn?: Omit<TranscriptTurn, "id">,
    ) => {
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
    [],
  );

  const startRecorder = useCallback(
    (
      stream: MediaStream,
      onChunk: (chunk: Blob) => void,
    ): MediaRecorder | null => {
      if (typeof MediaRecorder === "undefined") {
        return null;
      }
      try {
        const mimeType = supportedRecorderMimeType();
        const recorder = mimeType
          ? new MediaRecorder(stream, { mimeType })
          : new MediaRecorder(stream);
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
    },
    [],
  );

  const applyMicMute = useCallback(
    (nextMuted: boolean, options?: { emitEvent?: boolean }) => {
      const convo = conversationRef.current;
      micMutedRef.current = nextMuted;
      setMicMuted(nextMuted);

      if (convo) {
        try {
          convo.setMicMuted(nextMuted);
        } catch {
          // no-op
        }
        const stream = convo.input?.inputStream;
        if (stream) {
          for (const track of stream.getAudioTracks()) {
            track.enabled = !nextMuted;
          }
        }
      }

      const recorder = micRecorderRef.current;
      if (recorder) {
        try {
          if (nextMuted && recorder.state === "recording") {
            recorder.pause();
          } else if (!nextMuted && recorder.state === "paused") {
            recorder.resume();
          }
        } catch {
          // no-op
        }
      }

      if (options?.emitEvent !== false) {
        void pushEvent("mic_toggle", { muted: nextMuted });
      }
    },
    [pushEvent],
  );

  const appendTurn = useCallback(
    (speaker: "user" | "assistant", text: string) => {
      const trimmed = text.trim();
      if (!trimmed) {
        return;
      }

      if (
        speaker === "user" &&
        micMutedRef.current &&
        isPlaceholderUserUtterance(trimmed)
      ) {
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
          },
        );
        return [...current, nextTurn];
      });

      if (speaker === "user" && modeRef.current === "speaking") {
        void pushEvent("interruption", {
          reason: "user_barge_in_inferred",
        });
      }
    },
    [pushEvent],
  );

  const startSession = useCallback(async () => {
    if (conversationRef.current || isBusy) {
      return;
    }

    setError("");
    setIsBusy(true);
    setStatus("connecting");
    setMode("idle");
    setTranscript([]);
    setExportPreview("");

    micChunksRef.current = [];
    assistantChunksRef.current = [];

    try {
      const session = await callApi<SessionStartResponse>(
        "/api/session/start",
        {
          method: "POST",
        },
      );
      sessionIdRef.current = session.sessionId;
      setSessionId(session.sessionId);

      await pushEvent("session_started", {
        ui: "ui-blake",
      });

      const sdk = await import("@elevenlabs/client");
      const startWithAttempt = async (attempt: "primary" | "retry") => {
        const signed = await callApi<SignedUrlResponse>(
          "/api/eleven/signed-url",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ includeConversationId: true }),
          },
        );
        await pushEvent("connection_attempt", { attempt });
        const conversation = (await sdk.Conversation.startSession({
          signedUrl: signed.signedUrl,
          connectionType: "websocket",
          dynamicVariables: {
            local_session_id: session.sessionId,
          },
          customLlmExtraBody: {
            local_session_id: session.sessionId,
            source: "ui-blake",
          },
          overrides: {
            client: {
              source: "ui_blake",
              version: "v1",
            },
            ...(signed.voiceId
              ? {
                  tts: {
                    voiceId: signed.voiceId,
                  },
                }
              : {}),
          },
          onConnect: ({ conversationId: cid }: { conversationId: string }) => {
            setConversationId(cid);
            void pushEvent("eleven_connected", {
              conversationId: cid,
            });
          },
          onStatusChange: ({ status: nextStatus }: { status: UiStatus }) => {
            setStatus(nextStatus);
            void pushEvent("status", { status: nextStatus });
          },
          onModeChange: ({
            mode: nextMode,
          }: {
            mode: Exclude<UiMode, "idle">;
          }) => {
            modeRef.current = nextMode;
            setMode(nextMode);
            void pushEvent("mode", { mode: nextMode });
          },
          onMessage: ({
            source,
            message,
          }: {
            source: "user" | "ai";
            message: string;
          }) => {
            appendTurn(source === "ai" ? "assistant" : "user", message);
          },
          onError: (raw: unknown) => {
            const message = formatSdkError(raw);
            setError(message);
            console.error("[ui-blake] eleven sdk error", raw);
            void pushEvent("sdk_error", {
              message,
              raw: stringifyUnknown(raw),
              attempt,
            });
          },
          onDisconnect: (details: unknown) => {
            setStatus("disconnected");
            modeRef.current = "idle";
            setMode("idle");
            void pushEvent("eleven_disconnected", {
              details:
                typeof details === "object" && details
                  ? details
                  : { reason: "unknown" },
              attempt,
            });
          },
        })) as unknown as ConversationHandle;
        return { conversation, signed };
      };

      let conversation: ConversationHandle | null = null;
      let signedConversationId: string | null = null;
      try {
        const first = await startWithAttempt("primary");
        conversation = first.conversation;
        signedConversationId = first.signed.conversationId;
      } catch (firstErr) {
        const firstMessage =
          stringifyUnknown(firstErr) || "websocket_connect_failed";
        await pushEvent("connection_attempt_failed", {
          attempt: "primary",
          message: firstMessage,
        });
        const second = await startWithAttempt("retry");
        conversation = second.conversation;
        signedConversationId = second.signed.conversationId;
        setError("Initial connection failed; retry succeeded.");
      }

      if (!conversation) {
        throw new Error("Failed to initialize conversation");
      }

      conversationRef.current = conversation;
      setConversationId(conversation.getId?.() || signedConversationId || "");

      if (conversation.input?.inputStream) {
        micRecorderRef.current = startRecorder(
          conversation.input.inputStream,
          (chunk) => {
            micChunksRef.current.push(chunk);
          },
        );
      }

      const outputGain = conversation.output?.gain;
      const outputContext = conversation.output?.context;
      if (outputGain && outputContext) {
        const tapDestination = outputContext.createMediaStreamDestination();
        outputGain.connect(tapDestination);
        assistantTapDestinationRef.current = tapDestination;

        assistantRecorderRef.current = startRecorder(
          tapDestination.stream,
          (chunk) => {
            assistantChunksRef.current.push(chunk);
          },
        );
      }

      applyMicMute(false, { emitEvent: false });

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
  }, [appendTurn, applyMicMute, callApi, isBusy, pushEvent, startRecorder]);

  const stopSession = useCallback(async () => {
    if (!conversationRef.current || isStopping) {
      return;
    }
    setIsStopping(true);

    const convo = conversationRef.current;
    conversationRef.current = null;

    try {
      setStatus("disconnecting");
      applyMicMute(true, { emitEvent: false });
      await convo.endSession();

      const [micBlob, assistantBlob] = await Promise.all([
        stopRecorder(micRecorderRef.current, micChunksRef.current),
        stopRecorder(assistantRecorderRef.current, assistantChunksRef.current),
      ]);

      micRecorderRef.current = null;
      assistantRecorderRef.current = null;

      const tap = assistantTapDestinationRef.current;
      if (tap) {
        for (const track of tap.stream.getTracks()) {
          track.stop();
        }
      }
      assistantTapDestinationRef.current = null;

      const micBase64 = micBlob ? await blobToBase64(micBlob) : undefined;
      const assistantBase64 = assistantBlob
        ? await blobToBase64(assistantBlob)
        : undefined;

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
      setError(stringifyUnknown(err) || "Failed to stop session");
    } finally {
      setStatus("disconnected");
      modeRef.current = "idle";
      setMode("idle");
      setIsStopping(false);
    }
  }, [applyMicMute, callApi, isStopping, pushEvent]);

  const toggleMic = useCallback(() => {
    if (!conversationRef.current) {
      return;
    }
    applyMicMute(!micMutedRef.current);
  }, [applyMicMute]);

  const loadExport = useCallback(async () => {
    if (!sessionIdRef.current) {
      return;
    }
    try {
      const payload = await callApi<ExportPayload>(
        `/api/session/export?id=${encodeURIComponent(sessionIdRef.current)}`,
      );
      setExportPreview(JSON.stringify(payload, null, 2));
    } catch (err) {
      setError(stringifyUnknown(err) || "Export failed");
    }
  }, [callApi]);

  const downloadExport = useCallback(async () => {
    if (!sessionIdRef.current) {
      return;
    }
    try {
      const payload = await callApi<ExportPayload>(
        `/api/session/export?id=${encodeURIComponent(sessionIdRef.current)}`,
      );
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${sessionIdRef.current}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(stringifyUnknown(err) || "Export download failed");
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

  const hasActiveConversation = Boolean(conversationRef.current);
  const canStart = useMemo(
    () => !hasActiveConversation && !isBusy && status === "disconnected",
    [hasActiveConversation, isBusy, status],
  );
  const canStop = useMemo(
    () => hasActiveConversation && !isStopping,
    [hasActiveConversation, isStopping],
  );

  return (
    <main className="call-page">
      <section className="studio-grid">
        <article className="panel live-panel">
          <header className="hero-top">
            <div>
              <p className="eyebrow">Realtime Interview</p>
              <h1>AI Blake Studio</h1>
            </div>
            <span className={`status-pill ${status}`}>{status}</span>
          </header>

          <div
            className={`voice-stage ${status} ${mode} ${micMuted ? "mic-muted" : ""}`}
          >
            <svg
              className="voice-orbit-svg"
              viewBox="0 0 320 236"
              aria-hidden="true"
            >
              <defs>
                <linearGradient
                  id="coreGradient"
                  x1="0%"
                  y1="0%"
                  x2="100%"
                  y2="100%"
                >
                  <stop offset="0%" stopColor="#ffffff" />
                  <stop offset="100%" stopColor="#e7edf8" />
                </linearGradient>
                <linearGradient
                  id="waveGradient"
                  x1="20%"
                  y1="0%"
                  x2="100%"
                  y2="100%"
                >
                  <stop offset="0%" stopColor="#78d8c2" />
                  <stop offset="100%" stopColor="#2b78c8" />
                </linearGradient>
              </defs>

              <circle
                className="orbit-ring ring-outer"
                cx="160"
                cy="118"
                r="92"
              />
              <circle
                className="orbit-ring ring-inner"
                cx="160"
                cy="118"
                r="68"
              />

              <g className="orbit-node orbit-node-a">
                <g transform="translate(160 26)">
                  <circle className="node-shell" r="12.5" />
                  <path
                    className="node-icon"
                    d="M-4.5 -2.2h2.7l3.2-3.1v10.6L-1.8 2H-4.5zM3.1-1.4a3.6 3.6 0 0 1 0 4.8M4.9-3.1a6.1 6.1 0 0 1 0 8.2"
                  />
                </g>
              </g>
              <g className="orbit-node orbit-node-b">
                <g transform="translate(160 44)">
                  <circle className="node-shell" r="10" />
                  <path
                    className="node-icon"
                    d="M0-4.6v4M-2.5-1.4a2.5 2.5 0 1 0 5 0v-2a2.5 2.5 0 1 0-5 0zM-4.5 2.3a4.5 4.5 0 1 0 9 0"
                  />
                </g>
              </g>

              <circle className="core-glow" cx="160" cy="118" r="52" />
              <circle
                className="core-disc"
                cx="160"
                cy="118"
                r="42"
                fill="url(#coreGradient)"
              />
              <path
                className="wave wave-a"
                d="M132 118h8l6-12 6 24 6-18 6 12h24"
              />
              <path className="wave wave-b" d="M138 130h10l6-9 6 15 6-11h16" />
            </svg>

            <div className="voice-core">
              <span>
                {mode === "idle"
                  ? "Ready"
                  : mode === "speaking"
                    ? "AI Speaking"
                    : "Listening"}
              </span>
            </div>
            <div className="voice-bars" aria-hidden="true">
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
            </div>
          </div>

          <div className="call-controls">
            <button
              className="btn btn-connect"
              onClick={() => void startSession()}
              disabled={!canStart}
            >
              <PhoneIcon />
              <span>
                {status === "connecting" ? "Connecting..." : "Connect"}
              </span>
            </button>

            <button
              className="btn btn-mic"
              onClick={toggleMic}
              disabled={!hasActiveConversation}
            >
              {micMuted ? <MicOffIcon /> : <MicIcon />}
              <span>{micMuted ? "Unmute" : "Mute"}</span>
            </button>

            <button
              className="btn btn-end"
              onClick={() => void stopSession()}
              disabled={!canStop}
            >
              <PhoneIcon />
              <span>{isStopping ? "Ending..." : "End"}</span>
            </button>
          </div>

          <div className="meta-row">
            <div className="meta-item">
              <span>Session</span>
              <strong>{sessionId || "-"}</strong>
            </div>
            <div className="meta-item">
              <span>Conversation</span>
              <strong>{conversationId || "-"}</strong>
            </div>
            <div className="meta-item">
              <span>Mode</span>
              <strong>{mode}</strong>
            </div>
          </div>

          <section className="mini-export">
            <div className="panel-head mini-head">
              <h2>Session Export</h2>
              <span>Compact</span>
            </div>
            <div className="export-actions">
              <button
                className="btn btn-subtle"
                onClick={() => void loadExport()}
                disabled={!sessionId}
              >
                Preview JSON
              </button>
              <button
                className="btn btn-subtle"
                onClick={() => void downloadExport()}
                disabled={!sessionId}
              >
                Download
              </button>
            </div>
            <pre className="export-box">
              {exportPreview || "No export loaded."}
            </pre>
          </section>

          {error ? <p className="error-banner">{error}</p> : null}
        </article>

        <article className="panel transcript-panel">
          <div className="panel-head transcript-head">
            <h2>Live Transcript</h2>
            <span>{transcript.length} turns</span>
          </div>
          <div className="transcript-list">
            {transcript.length === 0 ? (
              <p className="empty">No transcript yet.</p>
            ) : null}
            {transcript.map((turn) => (
              <article key={turn.id} className={`turn-card ${turn.speaker}`}>
                <header>
                  <strong>
                    {turn.speaker === "assistant" ? "AI Blake" : "Blake"}
                  </strong>
                  <time>{new Date(turn.ts).toLocaleTimeString()}</time>
                </header>
                <p>{turn.text}</p>
              </article>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
