import type {
  Context,
  EnrollResult,
  NextStep,
  ResearchStudySummary,
  Schedule,
  WithdrawResult,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, credentials: "include" });
  if (!response.ok) {
    throw new Error(`Request to ${url} failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

function postJson<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getContext(): Promise<Context> {
  return request<Context>("/api/context");
}

export function listResearchStudies(): Promise<ResearchStudySummary[]> {
  return request<ResearchStudySummary[]>("/api/research-studies");
}

export function enrollPatient(studyId: string, patientId: string): Promise<EnrollResult> {
  return postJson<EnrollResult>(`/api/research-studies/${studyId}/enroll`, { patientId });
}

export function getSchedule(subjectId: string): Promise<Schedule> {
  return request<Schedule>(`/api/research-subjects/${subjectId}/schedule`);
}

export function completeVisit(
  subjectId: string,
  actionId: string,
  transitionChoice: string | null,
): Promise<Schedule> {
  return postJson<Schedule>(`/api/research-subjects/${subjectId}/visits/${actionId}/complete`, {
    transitionChoice,
  });
}

export function withdrawSubject(subjectId: string): Promise<WithdrawResult> {
  return postJson<WithdrawResult>(`/api/research-subjects/${subjectId}/withdraw`, undefined);
}

export type { NextStep };
