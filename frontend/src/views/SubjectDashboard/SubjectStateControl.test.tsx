import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import SubjectStateControl from "./SubjectStateControl";

describe("SubjectStateControl", () => {
  it("submits the selected state", async () => {
    const onUpdate = vi.fn();
    render(<SubjectStateControl currentState="eligible" busy={false} onUpdate={onUpdate} />);

    await userEvent.selectOptions(screen.getByLabelText("New state"), "on-study");
    await userEvent.click(screen.getByRole("button", { name: "Update state" }));

    expect(onUpdate).toHaveBeenCalledWith("on-study");
  });

  it("shows the subject's current state", () => {
    render(<SubjectStateControl currentState="screening" busy={false} onUpdate={vi.fn()} />);

    expect(screen.getByText("Current state: screening")).toBeInTheDocument();
  });

  it("disables the submit button until a state is chosen", () => {
    render(<SubjectStateControl currentState={null} busy={false} onUpdate={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Update state" })).toBeDisabled();
  });

  it("disables the submit button while busy", async () => {
    render(<SubjectStateControl currentState="eligible" busy={true} onUpdate={vi.fn()} />);

    await userEvent.selectOptions(screen.getByLabelText("New state"), "on-study");

    expect(screen.getByRole("button", { name: "Update state" })).toBeDisabled();
  });
});
