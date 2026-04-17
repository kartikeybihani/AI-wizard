"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";
import { useState } from "react";

import { SectionReveal } from "@/components/shared/SectionReveal";
import { design } from "@/styles/design";

export type NarrativeSectionProps = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  delay?: number;
  once?: boolean;
  offset?: number;
  className?: string;
  reducedMotion?: boolean;
  learnMore?: {
    summaryLabel?: string;
    content: ReactNode;
  };
};

export function NarrativeSection({
  title,
  subtitle,
  children,
  delay = 0,
  once = true,
  offset = 0.2,
  className,
  reducedMotion = false,
  learnMore,
}: NarrativeSectionProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <SectionReveal
      className={["narrative-section", className].filter(Boolean).join(" ")}
      delay={delay}
      once={once}
      offset={offset}
      reducedMotion={reducedMotion}
    >
      <div className="narrative-shell">
        <header className="narrative-header">
          <h2 className="narrative-title">{title}</h2>
          {subtitle ? <p className="narrative-subtitle">{subtitle}</p> : null}
        </header>

        <div className="narrative-body">
          <div>{children}</div>
        </div>

        {learnMore ? (
          <div className="narrative-learn-more">
            <button
              type="button"
              className={[
                "narrative-learn-trigger",
                expanded ? "is-open" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-expanded={expanded}
              onClick={() => setExpanded((current) => !current)}
            >
              <span>{learnMore.summaryLabel || "Learn more"}</span>
              <span className="narrative-learn-chevron" aria-hidden="true">
                ▾
              </span>
            </button>
            <AnimatePresence initial={false}>
              {expanded ? (
                <motion.div
                  className="narrative-learn-content"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{
                    duration: 0.35,
                    ease: design.motion.easePremium,
                  }}
                >
                  <div className="narrative-learn-content-inner">{learnMore.content}</div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        ) : null}
      </div>
    </SectionReveal>
  );
}
