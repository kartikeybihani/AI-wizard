"use client";

import { CTAButton } from "@/components/ui/CTAButton";

type HeroCtaRowProps = {
  primaryLabel: string;
  secondaryLabel: string;
  onPrimaryClick: () => void | Promise<void>;
  onSecondaryClick: () => void | Promise<void>;
  primaryDisabled?: boolean;
  secondaryDisabled?: boolean;
  primaryLoading?: boolean;
};

export function HeroCtaRow({
  primaryLabel,
  secondaryLabel,
  onPrimaryClick,
  onSecondaryClick,
  primaryDisabled = false,
  secondaryDisabled = false,
  primaryLoading = false,
}: HeroCtaRowProps) {
  return (
    <div className="hero-cta-row">
      <CTAButton
        variant="primary"
        onClick={onPrimaryClick}
        disabled={primaryDisabled}
        loading={primaryLoading}
      >
        {primaryLabel}
      </CTAButton>
      <CTAButton
        variant="secondary"
        onClick={onSecondaryClick}
        disabled={secondaryDisabled}
      >
        {secondaryLabel}
      </CTAButton>
    </div>
  );
}
