export const design = {
  colors: {
    bgPrimary: "#0a0e14",
    bgSurface: "#111820",
    bgElevated: "#1a2230",
    textPrimary: "#f0ece6",
    textSecondary: "#8a95a4",
    textTertiary: "#4a5568",
    accentIdle: "#f0ece6",
    accentListen: "#f4a261",
    accentSpeak: "#4ecdc4",
    accentMuted: "#6b7b8d",
    accentCosmos: "#9a4dff",
    accentUser: "#667eea",
    borderSubtle: "rgba(255, 255, 255, 0.06)",
    borderActive: "rgba(255, 255, 255, 0.12)",
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
    base: "#f0ece6",
    glow: "rgba(240,236,230,0.35)",
    emissive: "#f0ece6",
  },
  connecting: {
    base: "#f4a261",
    glow: "rgba(244,162,97,0.45)",
    emissive: "#f4a261",
  },
  connected: {
    base: "#f0ece6",
    glow: "rgba(240,236,230,0.35)",
    emissive: "#f0ece6",
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
