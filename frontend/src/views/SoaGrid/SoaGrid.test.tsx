import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getSoaGrid } from "../../api/client";
import type { SoaGridData } from "../../api/types";
import SoaGrid from "./SoaGrid";

vi.mock("../../api/client");

const GRID: SoaGridData = {
  id: "study-1",
  label: "UC1 Demo Study",
  visits: [
    { actionId: "screening-1", title: "Screening" },
    { actionId: "treatment-1", title: "Treatment" },
  ],
  activities: [
    { id: "act-vitals", label: "Vital Signs", type: "ActivityDefinition" },
    { id: "q-adas-cog", label: "ADAS-Cog", type: "Questionnaire" },
  ],
  matrix: {
    "act-vitals": ["screening-1", "treatment-1"],
    "q-adas-cog": ["screening-1"],
  },
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/studies/:studyId/soa-grid" element={<SoaGrid />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SoaGrid", () => {
  beforeEach(() => {
    vi.mocked(getSoaGrid).mockReset();
    vi.stubGlobal("print", vi.fn());
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:mock"), revokeObjectURL: vi.fn() });
  });

  it("renders one row per activity, one column per visit, and marks only the visits where an activity occurs", async () => {
    vi.mocked(getSoaGrid).mockResolvedValue(GRID);

    renderAt("/studies/study-1/soa-grid?plan=plan-1");

    expect(getSoaGrid).toHaveBeenCalledWith("study-1", "plan-1");

    const table = await screen.findByRole("table", { name: "Schedule of activities for UC1 Demo Study" });
    expect(within(table).getByRole("columnheader", { name: "Screening" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Treatment" })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "Vital Signs" })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "ADAS-Cog" })).toBeInTheDocument();

    // Vital Signs occurs at both visits; ADAS-Cog only at Screening.
    expect(within(table).getAllByLabelText("scheduled")).toHaveLength(3);
  });

  it("shows an error message when the grid fails to load", async () => {
    vi.mocked(getSoaGrid).mockRejectedValue(new Error("network error"));

    renderAt("/studies/study-1/soa-grid");

    expect(
      await screen.findByText("Could not load the schedule of activities for this study."),
    ).toBeInTheDocument();
  });

  it("triggers the browser print dialog from the Print button", async () => {
    vi.mocked(getSoaGrid).mockResolvedValue(GRID);
    renderAt("/studies/study-1/soa-grid");

    await userEvent.click(await screen.findByRole("button", { name: "Print" }));

    expect(window.print).toHaveBeenCalled();
  });
});
