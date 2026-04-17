import { fireEvent, render, screen } from "@testing-library/react";

import { NarrativeSection } from "./NarrativeSection";

describe("NarrativeSection", () => {
  it("renders title/subtitle and toggles learn-more content", () => {
    const { container } = render(
      <NarrativeSection
        title="Presence"
        subtitle="Story subtitle"
        learnMore={{ content: <p>Expanded details</p> }}
      >
        <div>Body content</div>
      </NarrativeSection>,
    );

    expect(screen.getByText("Presence")).toBeInTheDocument();
    expect(screen.getByText("Story subtitle")).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();

    const trigger = screen.getByRole("button", { name: /learn more/i });
    fireEvent.click(trigger);
    expect(screen.getByText("Expanded details")).toBeInTheDocument();

    const shell = container.querySelector(".narrative-shell");
    expect(shell).toBeInTheDocument();
  });
});
