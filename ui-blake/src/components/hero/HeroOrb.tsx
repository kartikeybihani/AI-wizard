"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import type { Group, Mesh, MeshStandardMaterial } from "three";

import { heroOrbPalette, type HeroOrbState } from "@/styles/design";

export type HeroOrbProps = {
  state: HeroOrbState;
  intensity?: number;
  reducedMotion?: boolean;
  onHover?: (hovered: boolean) => void;
};

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
  const ringRef = useRef<Mesh | null>(null);
  const orbiterGroupRef = useRef<Group | null>(null);
  const materialRef = useRef<MeshStandardMaterial | null>(null);
  const orbiterRef = useRef<Mesh | null>(null);

  const palette = heroOrbPalette[state];
  const level = clamp01(intensity);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const pulse = 0.035 + level * 0.08 + (hovered ? 0.035 : 0);
    const scale = 1 + Math.sin(t * (state === "speaking" ? 2.5 : 1.4)) * pulse;

    if (sphereRef.current) {
      sphereRef.current.scale.setScalar(scale);
    }
    if (ringRef.current) {
      if (!hovered) {
        ringRef.current.rotation.z += 0.004 + level * 0.01;
      }
    }
    if (orbiterGroupRef.current) {
      if (!hovered) {
        orbiterGroupRef.current.rotation.y += 0.02 + level * 0.03;
        orbiterGroupRef.current.rotation.x = Math.sin(t * 0.55) * 0.25;
      }
    }
    if (materialRef.current) {
      materialRef.current.emissiveIntensity =
        0.35 + level * 0.8 + (state === "speaking" ? 0.25 : 0) + (hovered ? 0.2 : 0);
    }
    if (orbiterRef.current) {
      orbiterRef.current.scale.setScalar(0.9 + level * 0.35);
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

      <mesh ref={ringRef} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.44, 0.024, 24, 180]} />
        <meshStandardMaterial
          color={palette.glow}
          emissive={palette.emissive}
          emissiveIntensity={0.4}
          transparent
          opacity={0.82}
        />
      </mesh>

      <group ref={orbiterGroupRef}>
        <mesh ref={orbiterRef} position={[1.74, 0, 0]}>
          <sphereGeometry args={[0.16, 32, 32]} />
          <meshStandardMaterial
            color={palette.base}
            emissive={palette.emissive}
            emissiveIntensity={0.5}
            roughness={0.25}
            metalness={0.15}
          />
        </mesh>
      </group>
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
  reducedMotion = false,
  onHover,
}: HeroOrbProps) {
  const [hovered, setHovered] = useState(false);
  const webglSupported = useMemo(() => {
    if (typeof document === "undefined") {
      return true;
    }
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  }, []);

  const safeIntensity = clamp01(intensity);
  const shouldFallback = reducedMotion || !webglSupported;

  return (
    <div
      className={`hero-orb hero-orb--${state} ${hovered ? "hero-orb--hovered" : ""}`}
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
      <svg className="hero-comet-tail" viewBox="0 0 100 100" aria-hidden="true">
        <path d="M 15 50 A 35 35 0 0 1 85 50" />
      </svg>
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
