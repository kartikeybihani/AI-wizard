import { fireEvent, render, screen } from "@testing-library/react";

import { CTAButton } from "./CTAButton";

describe("CTAButton", () => {
  it("fires click, ripple, and micro-burst", () => {
    const onClick = vi.fn();
    const { container } = render(
      <CTAButton variant="primary" onClick={onClick}>
        Launch
      </CTAButton>,
    );

    const button = screen.getByRole("button", { name: "Launch" });
    fireEvent.pointerDown(button, { clientX: 12, clientY: 9 });

    expect(container.querySelector(".cta-ripple")).toBeInTheDocument();
    expect(container.querySelector(".cta-microburst-line")).toBeInTheDocument();

    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
