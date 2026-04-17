import { render, screen } from "@testing-library/react";

import { SectionReveal } from "./SectionReveal";

describe("SectionReveal", () => {
  it("renders children and preserves reveal configuration attrs", () => {
    const { container } = render(
      <SectionReveal delay={0.2} once={false} offset={0.35}>
        <div>Reveal content</div>
      </SectionReveal>,
    );

    expect(screen.getByText("Reveal content")).toBeInTheDocument();

    const section = container.querySelector("section[data-reveal-delay='0.2']");
    expect(section).toBeInTheDocument();
    expect(section).toHaveAttribute("data-reveal-once", "false");
    expect(section).toHaveAttribute("data-reveal-offset", "0.35");
  });
});

