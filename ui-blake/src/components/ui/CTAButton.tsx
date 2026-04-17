"use client";

import type { CSSProperties, MouseEvent, ReactNode } from "react";
import { useState } from "react";

export type CTAButtonProps = {
  variant: "primary" | "secondary";
  onClick: () => void | Promise<void>;
  loading?: boolean;
  ripple?: boolean;
  microBurst?: boolean;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
};

type Ripple = {
  id: number;
  x: number;
  y: number;
};

type BurstLine = {
  id: number;
  angle: number;
};

function makeBurstLines(seed: number): BurstLine[] {
  return Array.from({ length: 7 }).map((_, index) => ({
    id: seed + index,
    angle: (360 / 7) * index + (index % 2 === 0 ? 8 : -6),
  }));
}

export function CTAButton({
  variant,
  onClick,
  loading = false,
  ripple = true,
  microBurst = true,
  disabled = false,
  className,
  children,
}: CTAButtonProps) {
  const [ripples, setRipples] = useState<Ripple[]>([]);
  const [burstLines, setBurstLines] = useState<BurstLine[]>([]);

  const addRipple = (event: MouseEvent<HTMLButtonElement>) => {
    if (!ripple) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const id = Date.now() + Math.floor(Math.random() * 999);
    const nextRipple: Ripple = {
      id,
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
    setRipples((current) => [...current, nextRipple]);
    window.setTimeout(() => {
      setRipples((current) =>
        current.filter((entry) => entry.id !== nextRipple.id),
      );
    }, 650);
  };

  const addMicroBurst = () => {
    if (!microBurst) {
      return;
    }
    const seed = Date.now();
    const lines = makeBurstLines(seed);
    setBurstLines(lines);
    window.setTimeout(() => {
      setBurstLines((current) =>
        current.filter((line) => !lines.some((added) => added.id === line.id)),
      );
    }, 580);
  };

  const onPointerDown = (event: MouseEvent<HTMLButtonElement>) => {
    if (loading || disabled) {
      return;
    }
    addRipple(event);
    addMicroBurst();
  };

  return (
    <button
      type="button"
      className={["cta-pill", `cta-pill--${variant}`, className]
        .filter(Boolean)
        .join(" ")}
      onClick={() => void onClick()}
      onPointerDown={onPointerDown}
      disabled={disabled || loading}
      data-ripple={ripple ? "enabled" : "disabled"}
      data-microburst={microBurst ? "enabled" : "disabled"}
    >
      <span className="cta-pill__label">{loading ? "Working..." : children}</span>
      {ripples.map((item) => (
        <span
          key={item.id}
          className="cta-ripple"
          style={{ left: item.x, top: item.y }}
          aria-hidden="true"
        />
      ))}
      <span className="cta-microburst" aria-hidden="true">
        {burstLines.map((line) => (
          <span
            key={line.id}
            className="cta-microburst-line"
            style={{ "--burst-angle": `${line.angle}deg` } as CSSProperties}
          />
        ))}
      </span>
    </button>
  );
}
