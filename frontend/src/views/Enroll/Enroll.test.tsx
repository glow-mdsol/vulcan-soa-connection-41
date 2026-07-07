import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { enrollPatient, getContext, getResearchStudy, listPatients } from "../../api/client";
import Enroll from "./Enroll";

vi.mock("../../api/client");

function renderAtStudy(studyId: string) {
  return render(
    <MemoryRouter initialEntries={[`/enroll/${studyId}`]}>
      <Routes>
        <Route path="/enroll/:studyId" element={<Enroll />} />
        <Route path="/subjects/:subjectId" element={<p>Subject dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Enroll", () => {
  beforeEach(() => {
    vi.mocked(getContext).mockReset();
    vi.mocked(enrollPatient).mockReset();
    vi.mocked(getResearchStudy).mockReset();
    vi.mocked(listPatients).mockReset();
  });

  it("enrolls the selected patient from the list", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: "patient-1", researchStudyId: null });
    vi.mocked(getResearchStudy).mockResolvedValue({
      id: "study-1",
      title: "UC1 Demo Study",
      status: "active",
      protocolReferences: ["PlanDefinition/plan-1"],
    });
    vi.mocked(listPatients).mockResolvedValue([
      { id: "patient-1", gender: "female", birthDate: "1980-01-01", deceased: null, active: true },
      { id: "patient-2", gender: "male", birthDate: null, deceased: null, active: true },
    ]);
    vi.mocked(enrollPatient).mockResolvedValue({
      researchSubjectId: "subj-1",
      schedule: { completed: [], current: [], nextSteps: [], ambiguous: false, visits: {} },
    });

    renderAtStudy("study-1");

  expect(await screen.findByRole("heading", { name: "UC1 Demo Study" })).toBeInTheDocument();
  expect(screen.getByText("study-1")).toBeInTheDocument();
  expect(screen.getByText("1 protocol is attached to this study.")).toBeInTheDocument();
    const select = await screen.findByLabelText("Patient");
    expect(select).toHaveValue("patient-1");

    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));

    expect(await screen.findByText("Subject dashboard")).toBeInTheDocument();
    expect(enrollPatient).toHaveBeenCalledWith("study-1", "patient-1");
  });

  it("lets the user choose a different patient when there is no launch context", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: null, researchStudyId: null });
    vi.mocked(getResearchStudy).mockResolvedValue({
      id: "study-1",
      title: "UC1 Demo Study",
      status: "active",
      protocolReferences: ["PlanDefinition/plan-1", "PlanDefinition/plan-2"],
    });
    vi.mocked(listPatients).mockResolvedValue([
      { id: "patient-1", gender: "female", birthDate: null, deceased: null, active: true },
      { id: "uc1-demo-patient", gender: "unknown", birthDate: null, deceased: null, active: true },
    ]);
    vi.mocked(enrollPatient).mockResolvedValue({
      researchSubjectId: "subj-2",
      schedule: { completed: [], current: [], nextSteps: [], ambiguous: false, visits: {} },
    });

    renderAtStudy("study-1");

    const select = await screen.findByLabelText("Patient");
    await userEvent.selectOptions(select, "uc1-demo-patient");
    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));

    expect(await screen.findByText("Subject dashboard")).toBeInTheDocument();
    expect(enrollPatient).toHaveBeenCalledWith("study-1", "uc1-demo-patient");
  });

  it("disables the Enroll button until patients have loaded", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: null, researchStudyId: null });
    vi.mocked(getResearchStudy).mockResolvedValue({
      id: "study-1",
      title: "UC1 Demo Study",
      status: "active",
      protocolReferences: [],
    });
    vi.mocked(listPatients).mockResolvedValue([]);

    renderAtStudy("study-1");

    expect(await screen.findByRole("button", { name: "Enroll" })).toBeDisabled();
  });

  it("shows a study details error when the study request fails", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: null, researchStudyId: null });
    vi.mocked(getResearchStudy).mockRejectedValue(new Error("network error"));
    vi.mocked(listPatients).mockResolvedValue([]);

    renderAtStudy("study-1");

    expect(await screen.findByText("Loading study details…")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load study details.");
  });
});
