import { fireEvent, render } from "@testing-library/react";

import { HeroOrb } from "./HeroOrb";

describe("HeroOrb", () => {
  it("renders deterministic fallback when reduced motion is enabled", () => {
    const { container } = render(
      <HeroOrb state="speaking" intensity={0.8} reducedMotion />,
    );

    const orb = container.querySelector("[data-orb-renderer='fallback']");
    expect(orb).toBeInTheDocument();
    expect(container.querySelector("svg.hero-orb-fallback")).toBeInTheDocument();
  });

  it("applies the requested orb state metadata", () => {
    const { container } = render(<HeroOrb state="connecting" reducedMotion />);
    const orb = container.querySelector("[data-orb-state='connecting']");
    expect(orb).toBeInTheDocument();
  });

  it("fires hover callback and toggles hover metadata", () => {
    const onHover = vi.fn();
    const { container } = render(
      <HeroOrb state="connected" reducedMotion onHover={onHover} />,
    );

    const orb = container.querySelector("[data-orb-state='connected']");
    expect(orb).toBeInTheDocument();
    if (!orb) {
      return;
    }

    fireEvent.pointerEnter(orb);
    expect(onHover).toHaveBeenCalledWith(true);
    expect(orb).toHaveAttribute("data-orb-hovered", "true");

    fireEvent.pointerLeave(orb);
    expect(onHover).toHaveBeenCalledWith(false);
    expect(orb).toHaveAttribute("data-orb-hovered", "false");
  });
});
