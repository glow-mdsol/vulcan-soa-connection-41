import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  completeVisit,
  enrollPatient,
  getContext,
  getSchedule,
  listResearchStudies,
  withdrawSubject,
} from "./client";

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  const response = { ok, status, json: () => Promise.resolve(body) } as Response;
  vi.mocked(fetch).mockResolvedValueOnce(response);
  return response;
}

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getContext calls GET /api/context with credentials included", async () => {
    mockFetchOnce({ patientId: "patient-1", researchStudyId: null });

    const context = await getContext();

    expect(context).toEqual({ patientId: "patient-1", researchStudyId: null });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/context");
    expect(init?.credentials).toBe("include");
  });

  it("listResearchStudies calls GET /api/research-studies", async () => {
    mockFetchOnce([{ id: "study-1", title: "UC1 Demo Study" }]);

    const studies = await listResearchStudies();

    expect(studies).toEqual([{ id: "study-1", title: "UC1 Demo Study" }]);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/research-studies");
  });

  it("enrollPatient posts the patientId as JSON", async () => {
    mockFetchOnce({
      researchSubjectId: "subj-1",
      schedule: { completed: [], current: [], nextSteps: [], ambiguous: false },
    });

    const result = await enrollPatient("study-1", "patient-1");

    expect(result.researchSubjectId).toBe("subj-1");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/research-studies/study-1/enroll");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ patientId: "patient-1" });
  });

  it("getSchedule calls GET /api/research-subjects/{id}/schedule", async () => {
    mockFetchOnce({ completed: [], current: [], nextSteps: [], ambiguous: false });

    await getSchedule("subj-1");

    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/research-subjects/subj-1/schedule");
  });

  it("completeVisit posts the transition choice", async () => {
    mockFetchOnce({ completed: [], current: [], nextSteps: [], ambiguous: false });

    await completeVisit("subj-1", "action-1", "day7-1");

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/research-subjects/subj-1/visits/action-1/complete");
    expect(JSON.parse(init?.body as string)).toEqual({ transitionChoice: "day7-1" });
  });

  it("withdrawSubject posts to the withdraw endpoint", async () => {
    mockFetchOnce({ id: "subj-1", subjectState: "withdrawn" });

    const result = await withdrawSubject("subj-1");

    expect(result).toEqual({ id: "subj-1", subjectState: "withdrawn" });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/research-subjects/subj-1/withdraw");
    expect(init?.method).toBe("POST");
  });

  it("throws when the response is not ok", async () => {
    mockFetchOnce({}, false, 401);

    await expect(getContext()).rejects.toThrow();
  });
});
