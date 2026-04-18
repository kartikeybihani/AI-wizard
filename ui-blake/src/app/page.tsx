"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ConstellationSVG } from "@/components/hero/Constellation";
import { HeroOrb } from "@/components/hero/HeroOrb";
import { NarrativeSection } from "@/components/shared/NarrativeSection";
import { Starfield } from "@/components/layout/Starfield";
import type { HeroOrbState } from "@/styles/design";

declare global {
  interface Window {
    __UI_BLAKE_MOCK_SESSION__?: boolean;
  }
}

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
  sendUserMessage?: (text: string) => void;
  getInputVolume?: () => number | Promise<number>;
  getOutputVolume?: () => number | Promise<number>;
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
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.572 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="7" y="5" width="3.2" height="14" rx="1.2" />
      <rect x="13.8" y="5" width="3.2" height="14" rx="1.2" />
    </svg>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`chevron ${expanded ? "expanded" : ""}`}
      aria-hidden="true"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="copy-icon-svg"
    >
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
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
  const [textInput, setTextInput] = useState<string>("");
  const [inputLevel, setInputLevel] = useState<number>(0);
  const [outputLevel, setOutputLevel] = useState<number>(0);
  const [debugOpen, setDebugOpen] = useState(false); // toggle debug area
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const [orbHovered, setOrbHovered] = useState(false);
  const [isDemoOpen, setIsDemoOpen] = useState(false);

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

  const transcriptRef = useRef<HTMLDivElement>(null);

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

      if (typeof window !== "undefined" && window.__UI_BLAKE_MOCK_SESSION__) {
        const mockConversation: ConversationHandle = {
          endSession: async () => {
            setStatus("disconnected");
          },
          setMicMuted: () => {
            // no-op in e2e mock mode
          },
          getId: () => `mock-${session.sessionId.slice(0, 8)}`,
          sendUserMessage: (text: string) => {
            appendTurn("user", text);
          },
          getInputVolume: () => 0.18,
          getOutputVolume: () => 0.58,
        };

        conversationRef.current = mockConversation;
        setConversationId(mockConversation.getId());
        setStatus("connected");
        modeRef.current = "listening";
        setMode("listening");
        applyMicMute(false, { emitEvent: false });
        await pushEvent("mock_connected", { enabled: true });
        return;
      }

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
          overrides: {
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

  const sendTextMessage = useCallback(() => {
    const convo = conversationRef.current;
    const value = textInput.trim();
    if (!convo || !value) {
      return;
    }
    if (typeof convo.sendUserMessage !== "function") {
      setError("sendUserMessage is unavailable in current SDK session.");
      return;
    }
    try {
      convo.sendUserMessage(value);
      setTextInput("");
      const ts = nowIso();
      void pushEvent(
        "manual_text_input",
        { text: value },
        {
          speaker: "user",
          text: value,
          ts,
        },
      );
    } catch (err) {
      setError(stringifyUnknown(err) || "Failed to send text message");
    }
  }, [pushEvent, textInput]);

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

  const openExportPreview = useCallback(async () => {
    setDebugOpen(true);
    if (!sessionIdRef.current) {
      setError("Start and end a session before previewing export.");
      return;
    }
    await loadExport();
  }, [loadExport]);

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

  useEffect(() => {
    if (!hasActiveConversation) {
      setInputLevel(0);
      setOutputLevel(0);
      return;
    }
    const interval = setInterval(() => {
      const convo = conversationRef.current;
      if (!convo) {
        return;
      }
      if (typeof convo.getInputVolume === "function") {
        try {
          void Promise.resolve(convo.getInputVolume())
            .then((v) => setInputLevel(Number.isFinite(v) ? v : 0))
            .catch(() => {
              // no-op
            });
        } catch {
          // no-op
        }
      }
      if (typeof convo.getOutputVolume === "function") {
        try {
          void Promise.resolve(convo.getOutputVolume())
            .then((v) => setOutputLevel(Number.isFinite(v) ? v : 0))
            .catch(() => {
              // no-op
            });
        } catch {
          // no-op
        }
      }
    }, 320);
    return () => clearInterval(interval);
  }, [hasActiveConversation]);

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    ) {
      return;
    }
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => {
      setPrefersReducedMotion(mediaQuery.matches);
    };
    update();
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", update);
      return () => mediaQuery.removeEventListener("change", update);
    }
    mediaQuery.addListener(update);
    return () => mediaQuery.removeListener(update);
  }, []);

  // Auto-scroll transcript when new turns arrive
  useEffect(() => {
    if (transcriptRef.current && transcript.length > 0) {
      transcriptRef.current.scrollTo({
        top: transcriptRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [transcript.length]);

  const copyToClipboard = async (value: string, field: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 1500);
    } catch {
      // Clipboard not available
    }
  };

  const hasTranscript = transcript.length > 0;
  const shouldUseSplitLayout =
    hasActiveConversation || Boolean(sessionId) || hasTranscript;
  const heroState = useMemo<HeroOrbState>(() => {
    if (!hasActiveConversation && status === "disconnected") {
      return "idle";
    }
    if (micMuted && hasActiveConversation) {
      return "muted";
    }
    if (mode === "speaking") {
      return "speaking";
    }
    if (mode === "listening") {
      return "listening";
    }
    if (status === "connecting") {
      return "connecting";
    }
    if (status === "connected") {
      return "connected";
    }
    if (status === "disconnecting") {
      return "disconnecting";
    }
    return "disconnected";
  }, [hasActiveConversation, micMuted, mode, status]);
  const heroCaption = useMemo(() => {
    if (heroState === "idle") {
      return "Ready for live interview";
    }
    if (heroState === "connecting") {
      return "Connecting to Blake...";
    }
    if (heroState === "connected") {
      return "Session active";
    }
    if (heroState === "listening") {
      return "Listening";
    }
    if (heroState === "speaking") {
      return "AI speaking";
    }
    if (heroState === "muted") {
      return "Mic paused";
    }
    if (heroState === "disconnecting") {
      return "Ending session...";
    }
    return "Session ended";
  }, [heroState]);

  return (
    <main
      className={`call-page ${orbHovered ? "is-orb-hovered" : ""} ${shouldUseSplitLayout ? "has-convo" : "no-convo"}`}
    >
      <Starfield reducedMotion={prefersReducedMotion} />
      {/* Grain overlay */}
      <div className="grain-overlay" aria-hidden="true" />
      <div className="landing-page-title" aria-label="Site title">
        No Magic Pill
      </div>
      <p className="landing-page-subtitle">
        Ask anything. Talk directly with Blake Mycoskie AI in real time.
      </p>
      <button
        type="button"
        className="page-demo-link"
        onClick={() => setIsDemoOpen(true)}
      >
        Demo
      </button>
      {isDemoOpen ? (
        <div
          className="demo-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Demo video"
          onClick={() => setIsDemoOpen(false)}
        >
          <div
            className="demo-modal-content"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="demo-modal-close"
              aria-label="Close demo video"
              onClick={() => setIsDemoOpen(false)}
            >
              ×
            </button>
            <video
              className="demo-modal-video"
              src="/Blake_v1.mp4"
              controls
              autoPlay
              preload="metadata"
            />
          </div>
        </div>
      ) : null}
      <div className="landing-grid">
        {/* Zone 1: The Presence — orb + title + controls */}
        <NarrativeSection
          className="presence-zone"
          delay={0}
          reducedMotion={prefersReducedMotion}
          title="AI Blake Studio"
          subtitle="Ask anything. Talk directly with Blake Mycoskie AI in real time."
          learnMore={{
            summaryLabel: "Learn more",
            content: (
              <>
                <p>
                  Presence fuses realtime audio state, celestial motion, and
                  actionable controls into one pilot view. Every pulse and glow
                  maps to an interview signal.
                </p>
                <ConstellationSVG reducedMotion={prefersReducedMotion} />
              </>
            ),
          }}
        >
          <div className="hero-orb-stage">
            <HeroOrb
              state={heroState}
              intensity={outputLevel}
              inputIntensity={inputLevel}
              reducedMotion={prefersReducedMotion}
              onHover={setOrbHovered}
            />
            <p className="hero-orb-caption mb-4">{heroCaption}</p>
          </div>

          {!shouldUseSplitLayout ? (
            <div className="call-controls control-row-main">
              <button
                className="btn btn-call"
                onClick={() => void startSession()}
                disabled={!canStart}
                aria-label="Call Blake"
              >
                <PhoneIcon />
                <span>
                  {status === "connecting"
                    ? "Connecting..."
                    : hasActiveConversation
                      ? "Session active"
                      : "Call Blake"}
                </span>
              </button>
            </div>
          ) : (
            <div className="control-stack">
              <div className="call-controls control-row-main control-row-top">
                <button
                  className="btn btn-call"
                  onClick={() => void startSession()}
                  disabled={!canStart}
                  aria-label="Call Blake"
                >
                  <PhoneIcon />
                  <span>
                    {status === "connecting"
                      ? "Connecting..."
                      : hasActiveConversation
                        ? "Session active"
                        : "Call Blake"}
                  </span>
                </button>
              </div>
              <div className="call-controls control-row-main control-row-mid">
                <button
                  className="btn btn-mic"
                  onClick={toggleMic}
                  disabled={!hasActiveConversation}
                >
                  <PauseIcon />
                  <span>{micMuted ? "Hold" : "Pause"}</span>
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
              <div className="call-controls control-row-main control-row-bottom">
                <button
                  className="btn btn-ghost btn-export-mini"
                  onClick={() => void openExportPreview()}
                  disabled={!sessionId}
                >
                  <EyeIcon />
                  <span>Export preview</span>
                </button>
              </div>
            </div>
          )}

          {/* Text input — only visible during active conversation */}
          {hasActiveConversation && (
            <div className="text-send-row">
              <input
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder="Type a message..."
                disabled={!hasActiveConversation}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    sendTextMessage();
                  }
                }}
              />
              <button
                className="btn btn-ghost"
                onClick={sendTextMessage}
                disabled={!hasActiveConversation || !textInput.trim()}
              >
                Send
              </button>
            </div>
          )}

          {error ? <p className="error-banner">{error}</p> : null}
        </NarrativeSection>

        {/* Zone 2: The Conversation — transcript */}
        <NarrativeSection
          className="conversation-zone transcript-box"
          delay={0.08}
          reducedMotion={prefersReducedMotion}
          title="Conversation"
          subtitle="Review each exchange with Blake AI while the studio stays live."
          learnMore={{
            summaryLabel: "Learn more",
            content: (
              <p>
                Conversation cards surface timing, speaker turn order, and key
                response cadence so you can evaluate flow quality in seconds.
              </p>
            ),
          }}
        >
          
          <div ref={transcriptRef} className="transcript-list">
            {!hasTranscript ? (
              <p className="transcript-empty">Conversation will appear here.</p>
            ) : null}
            {transcript.map((turn) => (
              <article key={turn.id} className={`turn-card ${turn.speaker}`}>
                <header className="turn-header">
                  <span className="turn-speaker">
                    {turn.speaker === "assistant" ? "AI Blake" : "Me"}
                  </span>
                  <div className="turn-accent" />
                  <time className="turn-time">
                    {new Date(turn.ts).toLocaleTimeString([], {
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </time>
                </header>
                <p className="turn-text">{turn.text}</p>
              </article>
            ))}
          </div>
        </NarrativeSection>
      </div>

      {/* Zone 3: Debug drawer (only in split layout) */}
      {shouldUseSplitLayout && (
        <NarrativeSection
          className="debug-zone"
          delay={0.16}
          reducedMotion={prefersReducedMotion}
          title="Diagnostics"
          subtitle="Operational telemetry and export artifacts for confident iteration."
          learnMore={{
            summaryLabel: "Learn more",
            content: (
              <p>
                Diagnostics bundles IDs, levels, and export previews to validate
                quality and preserve interview evidence without leaving the flow.
              </p>
            ),
          }}
        >
          <button
            className="debug-trigger"
            onClick={() => setDebugOpen(!debugOpen)}
            aria-expanded={debugOpen}
          >
            <span
              className={`debug-planet ${debugOpen ? "is-open" : ""}`}
              aria-hidden="true"
            />
            <span className="debug-trigger-label">Diagnostics Panel</span>
            <ChevronIcon expanded={debugOpen} />
          </button>

          {debugOpen && (
            <div className="debug-drawer">
              <div className="debug-grid">
                <div className="debug-section">
                  <h3>Session</h3>
                  <div className="debug-field">
                    <div className="debug-field-label">
                      <span>Session ID</span>
                      {sessionId && (
                        <button
                          className="btn-copy"
                          onClick={() => copyToClipboard(sessionId, "session")}
                          title="Copy session ID"
                        >
                          <CopyIcon />
                          {copiedField === "session" ? "Copied" : ""}
                        </button>
                      )}
                    </div>
                    <code className="mono-field">{sessionId || "—"}</code>
                  </div>
                  <div className="debug-field">
                    <div className="debug-field-label">
                      <span>Conversation ID</span>
                      {conversationId && (
                        <button
                          className="btn-copy"
                          onClick={() =>
                            copyToClipboard(conversationId, "conversation")
                          }
                          title="Copy conversation ID"
                        >
                          <CopyIcon />
                          {copiedField === "conversation" ? "Copied" : ""}
                        </button>
                      )}
                    </div>
                    <code className="mono-field">{conversationId || "—"}</code>
                  </div>
                  <div className="debug-field">
                    <div className="debug-field-label">
                      <span>Mode</span>
                    </div>
                    <code className="mono-field">{mode}</code>
                  </div>
                  <div className="debug-field">
                    <div className="debug-field-label">
                      <span>Status</span>
                    </div>
                    <code className="mono-field">{status}</code>
                  </div>
                </div>

                <div className="debug-section">
                  <h3>Audio Levels</h3>
                  <div className="vu-meters">
                    <div className="vu-item">
                      <span className="vu-label">Input</span>
                      <div className="vu-bar-track">
                        <div
                          className="vu-bar vu-bar-input"
                          style={{ "--vu-width": `${Math.round(inputLevel * 100)}%` } as React.CSSProperties}
                        />
                      </div>
                      <span className="vu-value">
                        {Math.round(inputLevel * 100)}%
                      </span>
                    </div>
                    <div className="vu-item">
                      <span className="vu-label">Output</span>
                      <div className="vu-bar-track">
                        <div
                          className="vu-bar vu-bar-output"
                          style={{ "--vu-width": `${Math.round(outputLevel * 100)}%` } as React.CSSProperties}
                        />
                      </div>
                      <span className="vu-value">
                        {Math.round(outputLevel * 100)}%
                      </span>
                    </div>
                  </div>
                </div>

                <div className="debug-section">
                  <h3>Export</h3>
                  <div className="export-actions">
                    <button
                      className="btn btn-ghost"
                      onClick={() => void loadExport()}
                      disabled={!sessionId}
                    >
                      <EyeIcon />
                      Preview
                    </button>
                    <button
                      className="btn btn-ghost"
                      onClick={() => void downloadExport()}
                      disabled={!sessionId}
                    >
                      <DownloadIcon />
                      Download
                    </button>
                  </div>
                  {exportPreview && (
                    <pre className="export-box">{exportPreview}</pre>
                  )}
                </div>
              </div>
            </div>
          )}
        </NarrativeSection>
      )}
    </main>
  );
}
