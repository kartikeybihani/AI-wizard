"use client";

import { motion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

import { design } from "@/styles/design";

export type SectionRevealProps = {
  children: ReactNode;
  delay?: number;
  once?: boolean;
  offset?: number;
  className?: string;
  reducedMotion?: boolean;
};

const revealVariants: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0 },
};

export function SectionReveal({
  children,
  delay = 0,
  once = true,
  offset = 0.2,
  className,
  reducedMotion = false,
}: SectionRevealProps) {
  return (
    <motion.section
      className={className}
      initial={false}
      animate="visible"
      variants={revealVariants}
      transition={{
        duration: reducedMotion ? 0 : design.motion.revealDuration,
        ease: design.motion.easePremium,
        delay: reducedMotion ? 0 : delay,
      }}
      data-reveal-delay={delay}
      data-reveal-once={once ? "true" : "false"}
      data-reveal-offset={offset}
    >
      {children}
    </motion.section>
  );
}
