"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { Mesh, MeshStandardMaterial } from "three";

import { heroOrbPalette, type HeroOrbState } from "@/styles/design";

export type HeroOrbProps = {
  state: HeroOrbState;
  intensity?: number;
  inputIntensity?: number;
  reducedMotion?: boolean;
  onHover?: (hovered: boolean) => void;
};

type TransitionFx =
  | "speak-onset"
  | "listen-onset"
  | "connect-sweep"
  | "settle"
  | null;

function clamp01(value: number): number {
  if (Number.isNaN(value)) {
    return 0;
  }
  if (value < 0) {
    return 0;
  }
  if (value > 1) {
    return 1;
  }
  return value;
}

function OrbScene({
  state,
  intensity,
  hovered,
}: {
  state: HeroOrbState;
  intensity: number;
  hovered: boolean;
}) {
  const sphereRef = useRef<Mesh | null>(null);
  const materialRef = useRef<MeshStandardMaterial | null>(null);

  const palette = heroOrbPalette[state];
  const level = clamp01(intensity);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const pulse = 0.035 + level * 0.08 + (hovered ? 0.035 : 0);
    const scale = 1 + Math.sin(t * (state === "speaking" ? 2.5 : 1.4)) * pulse;

    if (sphereRef.current) {
      sphereRef.current.scale.setScalar(scale);
    }
    if (materialRef.current) {
      const isQuietState = state === "idle" || state === "connected";
      const baseEmissive = isQuietState ? 0.14 : 0.35;
      const levelGain = isQuietState ? 0.22 : 0.8;
      materialRef.current.emissiveIntensity =
        baseEmissive +
        level * levelGain +
        (state === "speaking" ? 0.25 : 0) +
        (hovered ? 0.12 : 0);
    }
  });

  return (
    <>
      <ambientLight intensity={0.6} />
      <pointLight position={[2.2, 2.6, 2]} intensity={1.25} color={palette.glow} />
      <pointLight position={[-2, -2, -2]} intensity={0.5} color="#c7d3e3" />

      <mesh ref={sphereRef}>
        <sphereGeometry args={[0.96, 72, 72]} />
        <meshStandardMaterial
          ref={materialRef}
          color={palette.base}
          emissive={palette.emissive}
          emissiveIntensity={0.45}
          roughness={0.38}
          metalness={0.2}
        />
      </mesh>

    </>
  );
}

function FallbackOrb({ state }: { state: HeroOrbState }) {
  return (
    <svg viewBox="0 0 320 320" className={`hero-orb-fallback hero-orb-fallback--${state}`}>
      <defs>
        <linearGradient id="heroCoreGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#e7edf8" />
        </linearGradient>
      </defs>
      <circle className="hero-orb-fallback__ring" cx="160" cy="160" r="112" />
      <circle
        className="hero-orb-fallback__ring hero-orb-fallback__ring--inner"
        cx="160"
        cy="160"
        r="82"
      />
      <circle className="hero-orb-fallback__glow" cx="160" cy="160" r="58" />
      <circle className="hero-orb-fallback__core" cx="160" cy="160" r="46" fill="url(#heroCoreGradient)" />
      <path className="hero-orb-fallback__wave" d="M132 160h10l6-14 7 28 6-20 7 14h26" />
      <path
        className="hero-orb-fallback__wave hero-orb-fallback__wave--secondary"
        d="M138 174h12l6-10 6 16 7-12h18"
      />
    </svg>
  );
}

export function HeroOrb({
  state,
  intensity = 0,
  inputIntensity = 0,
  reducedMotion = false,
  onHover,
}: HeroOrbProps) {
  const [hovered, setHovered] = useState(false);
  const [transitionFx, setTransitionFx] = useState<TransitionFx>(null);
  const [transitionKey, setTransitionKey] = useState(0);
  const previousStateRef = useRef<HeroOrbState>(state);
  const webglSupported = useMemo(() => {
    if (typeof document === "undefined") {
      return true;
    }
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  }, []);

  const safeOutputIntensity = clamp01(intensity);
  const safeInputIntensity = clamp01(inputIntensity);
  const activeSignalLevel = useMemo(() => {
    if (state === "listening") {
      // Stronger listening response so input volume visibly drives arc/icon growth.
      const boostedInput = Math.pow(safeInputIntensity, 0.48);
      const noiseGateFloor = safeInputIntensity > 0.008 ? 0.16 : 0.04;
      return noiseGateFloor + boostedInput * 1.22;
    }
    if (state === "speaking") {
      return safeOutputIntensity;
    }
    if (state === "connecting") {
      return 0.5;
    }
    if (state === "connected") {
      return 0.16 + Math.max(safeInputIntensity, safeOutputIntensity) * 0.24;
    }
    if (state === "idle") {
      return 0.08;
    }
    if (state === "muted") {
      return 0.04;
    }
    return 0.02;
  }, [safeInputIntensity, safeOutputIntensity, state]);
  const safeIntensity = clamp01(activeSignalLevel);
  const shouldFallback = reducedMotion || !webglSupported;
  const orbStyle = {
    "--signal-level": safeIntensity.toFixed(3),
  } as CSSProperties;

  useEffect(() => {
    const previousState = previousStateRef.current;
    if (previousState === state) {
      return;
    }

    let nextTransition: TransitionFx = null;
    if (state === "speaking") {
      nextTransition = "speak-onset";
    } else if (state === "listening") {
      nextTransition = "listen-onset";
    } else if (state === "connecting") {
      nextTransition = "connect-sweep";
    } else if (previousState === "speaking") {
      nextTransition = "settle";
    }

    setTransitionFx(nextTransition);
    if (nextTransition) {
      setTransitionKey((current) => current + 1);
    }

    previousStateRef.current = state;
  }, [state]);

  return (
    <div
      className={`hero-orb hero-orb--${state} ${hovered ? "hero-orb--hovered" : ""}`}
      style={orbStyle}
      onPointerEnter={() => {
        setHovered(true);
        onHover?.(true);
      }}
      onPointerLeave={() => {
        setHovered(false);
        onHover?.(false);
      }}
      data-orb-state={state}
      data-orb-renderer={shouldFallback ? "fallback" : "r3f"}
      data-orb-hovered={hovered ? "true" : "false"}
    >
      {transitionFx ? (
        <span
          key={`${transitionFx}-${transitionKey}`}
          className={`hero-orb-transition hero-orb-transition--${transitionFx}`}
          aria-hidden="true"
        />
      ) : null}
      <svg className="voice-orbit-svg hero-signal-orbit" viewBox="0 0 320 320" aria-hidden="true">
        <circle className="orbit-ring" cx="160" cy="160" r="114" />
        <circle className="orbit-ring ring-inner" cx="160" cy="160" r="92" />
        <circle className="core-glow" cx="160" cy="160" r="54" />
        <circle className="waveform-ring hero-signal-arc hero-signal-arc--outer" cx="160" cy="160" r="76" />
        <circle className="waveform-ring hero-signal-arc hero-signal-arc--inner" cx="160" cy="160" r="60" />
      </svg>
      <div className="hero-signal-core" aria-hidden="true">
        <svg className="hero-podcast-icon" viewBox="0 0 28 28">
          <circle className="hero-podcast-dot" cx="14" cy="14" r="2.2" />
          <path className="hero-podcast-stem" d="M14 16.8v4.2" />
          <path className="hero-podcast-arc" d="M9.8 14a4.2 4.2 0 0 1 8.4 0" />
          <path className="hero-podcast-arc" d="M7.2 14a6.8 6.8 0 0 1 13.6 0" />
          <path className="hero-podcast-arc hero-podcast-arc--outer" d="M4.8 14a9.2 9.2 0 0 1 18.4 0" />
        </svg>
      </div>
      {shouldFallback ? (
        <FallbackOrb state={state} />
      ) : (
        <Canvas camera={{ position: [0, 0, 4.4], fov: 38 }}>
          <OrbScene state={state} intensity={safeIntensity} hovered={hovered} />
        </Canvas>
      )}
    </div>
  );
}
