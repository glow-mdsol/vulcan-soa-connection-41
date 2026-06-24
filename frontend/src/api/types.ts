export interface Context {
  patientId: string | null;
  researchStudyId: string | null;
}

export interface ResearchStudySummary {
  id: string;
  title: string;
}

export interface NextStep {
  actionId: string;
  title: string;
  transitionType: string | null;
}

export interface Schedule {
  completed: string[];
  current: string[];
  nextSteps: NextStep[];
  ambiguous: boolean;
}

export interface EnrollResult {
  researchSubjectId: string;
  schedule: Schedule;
}

export interface WithdrawResult {
  id: string;
  subjectState: string;
}
