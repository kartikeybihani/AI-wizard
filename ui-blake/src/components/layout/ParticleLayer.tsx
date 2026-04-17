"use client";

import { useMemo, type CSSProperties } from "react";

const particleCount = 18;

export function AmbientParticleLayer({ reducedMotion = false }: { reducedMotion?: boolean }) {
  const particles = useMemo(
    () =>
      Array.from({ length: particleCount }).map((_, index) => {
        const seed = index + 1;
        return {
          id: `p-${seed}`,
          x: ((seed * 73) % 100) + (seed % 2 ? -4 : 3),
          y: ((seed * 41) % 100) + (seed % 3 ? 2 : -3),
          size: 1.4 + (seed % 4) * 0.7,
          duration: 10 + (seed % 6) * 1.3,
          delay: (seed % 5) * -1.4,
          driftX: ((seed % 5) - 2) * 12,
          driftY: ((seed % 7) - 3) * 14,
        };
      }),
    [],
  );

  return (
    <div
      className={[
        "particle-layer",
        reducedMotion ? "is-reduced-motion" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-hidden="true"
    >
      {particles.map((particle) => (
        <span
          key={particle.id}
          className="particle-dot"
          style={
            {
              "--particle-x": `${particle.x}%`,
              "--particle-y": `${particle.y}%`,
              "--particle-size": `${particle.size}px`,
              "--particle-drift-duration": `${particle.duration}s`,
              "--particle-drift-delay": `${particle.delay}s`,
              "--particle-drift-x": `${particle.driftX}px`,
              "--particle-drift-y": `${particle.driftY}px`,
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
}
