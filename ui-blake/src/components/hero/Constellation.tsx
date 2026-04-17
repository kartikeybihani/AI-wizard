"use client";

import { useInView } from "framer-motion";
import { useMemo, useRef, type CSSProperties } from "react";

import { design } from "@/styles/design";

type Point = {
  id: string;
  x: number;
  y: number;
  label: string;
  glyph: string;
};

const points: Point[] = [
  { id: "voice", x: 76, y: 78, label: "Voice", glyph: "🎙" },
  { id: "live", x: 176, y: 58, label: "Live", glyph: "⚡" },
  { id: "memory", x: 290, y: 98, label: "Memory", glyph: "🧠" },
  { id: "insight", x: 248, y: 188, label: "Insights", glyph: "📈" },
  { id: "control", x: 114, y: 194, label: "Control", glyph: "🎛" },
];

const links: Array<[string, string]> = [
  ["voice", "live"],
  ["live", "memory"],
  ["memory", "insight"],
  ["insight", "control"],
  ["control", "voice"],
  ["live", "insight"],
];

function distance(a: Point, b: Point): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

export function ConstellationSVG({ reducedMotion = false }: { reducedMotion?: boolean }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const drawn = useInView(containerRef, { amount: 0.45, once: true });

  const linkData = useMemo(() => {
    return links.map(([from, to], index) => {
      const a = points.find((point) => point.id === from);
      const b = points.find((point) => point.id === to);
      if (!a || !b) {
        return null;
      }
      const len = Math.max(1, distance(a, b));
      return {
        key: `${from}-${to}`,
        d: `M ${a.x} ${a.y} L ${b.x} ${b.y}`,
        len,
        delayMs: Math.round(index * 85),
      };
    }).filter(Boolean) as Array<{ key: string; d: string; len: number; delayMs: number }>;
  }, []);

  return (
    <div
      ref={containerRef}
      className={[
        "constellation-svg",
        drawn ? "is-drawn" : "",
        reducedMotion ? "is-reduced-motion" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={
        {
          "--constellation-draw-duration": `${design.motion.constellationDrawDuration || 0.8}s`,
        } as CSSProperties
      }
      aria-hidden="true"
    >
      <svg viewBox="0 0 360 252" role="img" aria-label="Constellation map of Blake features">
        <g className="constellation-links">
          {linkData.map((line) => (
            <path
              key={line.key}
              d={line.d}
              style={
                {
                  "--path-len": line.len,
                  "--path-delay": `${line.delayMs}ms`,
                } as CSSProperties
              }
            />
          ))}
        </g>

        <g className="constellation-nodes">
          {points.map((point) => (
            <g key={point.id} transform={`translate(${point.x}, ${point.y})`} className="constellation-node">
              <circle r="7.2" />
              <text className="constellation-glyph" x="0" y="-14" textAnchor="middle">
                {point.glyph}
              </text>
              <text className="constellation-label" x="0" y="22" textAnchor="middle">
                {point.label}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
