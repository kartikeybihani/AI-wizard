export const design = {
  colors: {
    // — Backgrounds —
    bgPrimary: "#0a0e14",
    bgSurface: "#111820",
    bgElevated: "#1a2230",
    // — Text —
    textPrimary: "#f0ece6",
    textSecondary: "#8a95a4",
    textTertiary: "#4a5568",
    // — Accents —
    accentIdle: "#f0ece6",
    accentListen: "#f4a261",
    accentSpeak: "#4ecdc4",
    accentMuted: "#6b7b8d",
    accentCosmos: "#9a4dff",
    accentUser: "#667eea",
    // — Borders —
    borderSubtle: "rgba(255, 255, 255, 0.06)",
    borderActive: "rgba(255, 255, 255, 0.12)",
    // — Semantic (were hardcoded in CSS) —
    statusConnected: "#34c759",
    error: "#e8675a",
    errorBg: "rgba(210, 78, 59, 0.06)",
    errorBorder: "rgba(232, 103, 90, 0.2)",
    kickerLabel: "#ccb7ff",
    debugDrawerLabel: "#e0d4f5",
    // — Button: Primary (Connect) gradient —
    btnConnectFrom: "#5eead4",
    btnConnectTo: "#2dd4bf",
    btnConnectHoverFrom: "#7ff4e0",
    btnConnectHoverTo: "#3fdcc8",
    btnConnectDisabledBorder: "#64748b",
    btnConnectDisabledFrom: "#334155",
    btnConnectDisabledTo: "#1e293b",
    btnConnectDisabledText: "#dbe5f2",
    // — Button: Danger (End) —
    btnEndBorder: "rgba(210, 78, 59, 0.25)",
    btnEndBorderHover: "rgba(210, 78, 59, 0.45)",
    btnEndGlow: "rgba(210, 78, 59, 0.1)",
    btnEndBgHover: "rgba(210, 78, 59, 0.08)",
    btnEndDisabledBorder: "rgba(232, 103, 90, 0.5)",
    btnEndDisabledText: "#f5b9b1",
    btnEndDisabledBg: "rgba(86, 37, 33, 0.66)",
    // — Button: Disabled (generic) —
    btnDisabledBorder: "rgba(148, 163, 184, 0.52)",
    btnDisabledBg: "rgba(30, 42, 58, 0.88)",
    btnDisabledText: "#d4dceb",
    // -- Starfield background --
    starfieldFrom: "#06090f",
    starfieldMid: "#0a0e14",
    starfieldTo: "#090d15",
    // -- Narrative card --
    narrativeBgStart: "rgba(17, 26, 39, 0.96)",
    narrativeBgEnd: "rgba(12, 19, 30, 0.94)",
    debugDrawerBgStart: "rgba(22, 16, 40, 0.96)",
    debugDrawerBgEnd: "rgba(14, 10, 26, 0.94)",
    debugDrawerHoverBgStart: "rgba(40, 24, 68, 0.96)",
    debugDrawerHoverBgEnd: "rgba(28, 16, 52, 0.96)",
  },
  spacing: {
    sectionGap: "48px",
    containerX: "20px",
    containerY: "60px",
  },
  radius: {
    sm: "8px",
    md: "10px",
    lg: "12px",
    pill: "9999px",
  },
  shadows: {
    glowTeal: "0 0 30px rgba(78, 205, 196, 0.16)",
    glowAmber: "0 0 30px rgba(244, 162, 97, 0.14)",
    glowCosmos: "0 0 16px rgba(154, 77, 255, 0.6)",
    orbContainer: "0 0 24px rgba(0, 0, 0, 0.45)",
    glassInset: "inset 0 1px 0 rgba(255, 255, 255, 0.08)",
  },
  motion: {
    easePremium: [0.22, 1, 0.36, 1] as const,
    revealDuration: 0.55,
    heroEntranceDuration: 1.2,
    constellationDrawDuration: 0.8,
    particleDriftDuration: 12,
    rippleDurationMs: 560,
  },
  zIndex: {
    background: 0,
    content: 10,
    overlay: 100,
  },
  font: {
    body: "var(--font-body)",
    heading: "var(--font-heading)",
    ui: "var(--font-body)",
    mono: "var(--font-mono)",
  },
} as const;

export type HeroOrbState =
  | "idle"
  | "connecting"
  | "connected"
  | "listening"
  | "speaking"
  | "muted"
  | "disconnecting"
  | "disconnected";

export const heroOrbPalette: Record<
  HeroOrbState,
  {
    base: string;
    glow: string;
    emissive: string;
  }
> = {
  idle: {
    base: "#1b2735",
    glow: "rgba(96,128,158,0.24)",
    emissive: "#24364b",
  },
  connecting: {
    base: "#f4a261",
    glow: "rgba(244,162,97,0.45)",
    emissive: "#f4a261",
  },
  connected: {
    base: "#223142",
    glow: "rgba(112,142,171,0.26)",
    emissive: "#2d425c",
  },
  listening: {
    base: "#f4a261",
    glow: "rgba(244,162,97,0.45)",
    emissive: "#f4a261",
  },
  speaking: {
    base: "#4ecdc4",
    glow: "rgba(78,205,196,0.5)",
    emissive: "#4ecdc4",
  },
  muted: {
    base: "#6b7b8d",
    glow: "rgba(107,123,141,0.35)",
    emissive: "#6b7b8d",
  },
  disconnecting: {
    base: "#6b7b8d",
    glow: "rgba(107,123,141,0.35)",
    emissive: "#6b7b8d",
  },
  disconnected: {
    base: "#6b7b8d",
    glow: "rgba(107,123,141,0.28)",
    emissive: "#6b7b8d",
  },
};
