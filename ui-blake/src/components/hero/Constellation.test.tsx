import { render } from "@testing-library/react";

import { ConstellationSVG } from "./Constellation";

describe("ConstellationSVG", () => {
  it("renders constellation nodes and links", () => {
    const { container } = render(<ConstellationSVG reducedMotion />);

    const root = container.querySelector(".constellation-svg");
    expect(root).toBeInTheDocument();
    expect(root).toHaveClass("is-reduced-motion");

    const links = container.querySelectorAll(".constellation-links path");
    const nodes = container.querySelectorAll(".constellation-node");
    expect(links.length).toBeGreaterThan(3);
    expect(nodes.length).toBeGreaterThan(3);
  });
});
