"use client";

import { AmbientParticleLayer } from "@/components/layout/ParticleLayer";

export function Starfield({ reducedMotion = false }: { reducedMotion?: boolean }) {
  return (
    <div className="starfield" aria-hidden="true">
      <div className="starfield-layer starfield-layer--near" />
      <div className="starfield-layer starfield-layer--far" />
      <AmbientParticleLayer reducedMotion={reducedMotion} />
    </div>
  );
}
