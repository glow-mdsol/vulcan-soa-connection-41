import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { VisitDetail } from "../../api/types";
import VisitCard from "./VisitCard";

function noopHandlers() {
  return {
    onPlan: vi.fn(),
    onOrder: vi.fn(),
    onSchedule: vi.fn(),
    onRespond: vi.fn(),
    onPerform: vi.fn(),
    onCompleteTask: vi.fn(),
    onCompleteVisit: vi.fn(),
  };
}

describe("VisitCard", () => {
  it("shows the gate button for the current phase and marks the stepper", () => {
    const handlers = noopHandlers();
    render(<VisitCard actionId="E1" detail={{ phase: "proposed" }} {...handlers} />);

    expect(screen.getByRole("button", { name: "Accept proposal" })).toBeInTheDocument();
    const proposedInStepper = screen.getAllByText("proposed").find((el) => el.tagName === "LI");
    expect(proposedInStepper).toHaveAttribute("aria-current", "step");
  });

  it("shows participant responses while scheduled and disables an accepted participant", async () => {
    const handlers = noopHandlers();
    const detail: VisitDetail = {
      phase: "scheduled",
      participants: [
        { role: "patient", status: "accepted" },
        { role: "site", status: "needs-action" },
      ],
    };
    render(<VisitCard actionId="E1" detail={detail} {...handlers} />);

    expect(screen.getByRole("button", { name: "Patient accepts" })).toBeDisabled();
    const siteButton = screen.getByRole("button", { name: "Site confirms" });
    await userEvent.click(siteButton);
    expect(handlers.onRespond).toHaveBeenCalledWith("site");
  });

  it("renders the task checklist while performing with Complete visit always enabled", async () => {
    const handlers = noopHandlers();
    const detail: VisitDetail = {
      phase: "performing",
      tasks: [
        { id: "t-1", description: "Vital signs", status: "ready" },
        { id: "t-2", description: "Informed consent", status: "completed" },
      ],
    };
    render(<VisitCard actionId="E1" detail={detail} {...handlers} />);

    await userEvent.click(screen.getByRole("button", { name: "Done: Vital signs" }));
    expect(handlers.onCompleteTask).toHaveBeenCalledWith("t-1");
    expect(screen.queryByRole("button", { name: "Done: Informed consent" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Complete visit" }));
    expect(handlers.onCompleteVisit).toHaveBeenCalled();
  });

  it("shows the visit title when provided and keeps the action id visible", () => {
    const handlers = noopHandlers();
    render(
      <VisitCard actionId="E1" title="Screening" detail={{ phase: "proposed" }} {...handlers} />,
    );

    expect(screen.getByText("Screening")).toBeInTheDocument();
    expect(screen.getByText("E1")).toBeInTheDocument();
  });

  it("falls back to the action id as the card heading when no title is given", () => {
    const handlers = noopHandlers();
    render(<VisitCard actionId="E1" detail={{ phase: "proposed" }} {...handlers} />);

    expect(screen.getByLabelText("Visit E1")).toBeInTheDocument();
  });
});
