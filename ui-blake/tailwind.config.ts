import type { Config } from "tailwindcss";

import { design } from "./src/styles/design";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          bg: design.colors.bgPrimary,
          surface: design.colors.bgSurface,
          elevated: design.colors.bgElevated,
          text: design.colors.textPrimary,
          subtle: design.colors.textSecondary,
          tertiary: design.colors.textTertiary,
          listen: design.colors.accentListen,
          speak: design.colors.accentSpeak,
          muted: design.colors.accentMuted,
          idle: design.colors.accentIdle,
          cosmos: design.colors.accentCosmos,
        },
      },
      fontFamily: {
        ui: [design.font.body, "Inter", "Avenir Next", "sans-serif"],
        heading: [design.font.heading, "Space Grotesk", "sans-serif"],
        mono: [design.font.mono, "IBM Plex Mono", "monospace"],
      },
      borderRadius: {
        sm: design.radius.sm,
        md: design.radius.md,
        lg: design.radius.lg,
        pill: design.radius.pill,
      },
      boxShadow: {
        "glow-teal": design.shadows.glowTeal,
        "glow-amber": design.shadows.glowAmber,
        "glow-cosmos": design.shadows.glowCosmos,
        orb: design.shadows.orbContainer,
        "glass-inset": design.shadows.glassInset,
      },
      transitionTimingFunction: {
        premium: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
};

export default config;
