import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Timeline from "./Timeline";

describe("Timeline", () => {
  it("renders done, active, and upcoming nodes in order with titles", () => {
    render(
      <Timeline
        completed={["a-1"]}
        current={["b-2"]}
        nextSteps={[{ actionId: "c-3", title: "Day 7", transitionType: "SS" }]}
        titles={{ "a-1": "Screening", "b-2": "Treatment Day 1" }}
      />,
    );

    const rail = screen.getByRole("navigation", { name: "Study timeline" });
    const nodes = within(rail).getAllByRole("listitem");
    expect(nodes.map((n) => n.textContent)).toEqual(["Screening", "Treatment Day 1", "Day 7"]);
    expect(nodes[0].className).toContain("done");
    expect(nodes[1].className).toContain("active");
    expect(nodes[2].className).toContain("upcoming");
  });

  it("falls back to action ids when titles are missing", () => {
    render(<Timeline completed={["a-1"]} current={[]} nextSteps={[]} />);
    expect(screen.getByText("a-1")).toBeInTheDocument();
  });
});
