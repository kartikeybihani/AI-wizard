"use client";

import { useEffect, useRef } from "react";

import { AmbientParticleLayer } from "@/components/layout/ParticleLayer";

export function Starfield({ reducedMotion = false }: { reducedMotion?: boolean }) {
  const starfieldRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const node = starfieldRef.current;
    if (!node) {
      return;
    }

    const updateParallax = () => {
      const shift = Math.min(window.scrollY * 0.12, 120);
      node.style.setProperty("--starfield-shift", `${shift.toFixed(2)}px`);
      frameRef.current = null;
    };

    const onScroll = () => {
      if (frameRef.current !== null) {
        return;
      }
      frameRef.current = window.requestAnimationFrame(updateParallax);
    };

    updateParallax();
    window.addEventListener("scroll", onScroll, { passive: true });

    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
      }
    };
  }, []);

  return (
    <div className="starfield" ref={starfieldRef} aria-hidden="true">
      <div className="starfield-layer starfield-layer--near" />
      <div className="starfield-layer starfield-layer--far" />
      <AmbientParticleLayer reducedMotion={reducedMotion} />
    </div>
  );
}
