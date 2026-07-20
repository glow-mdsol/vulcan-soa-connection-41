import { useState } from "react";

// THO ValueSet/research-subject-state (code system v1.0.1) — must match
// backend/src/vulcan_soa/tracking.py RESEARCH_SUBJECT_STATES.
const STATE_OPTIONS = [
  { code: "candidate", label: "Candidate" },
  { code: "eligible", label: "Eligible" },
  { code: "follow-up", label: "Follow-up" },
  { code: "ineligible", label: "Ineligible" },
  { code: "not-registered", label: "Not Registered" },
  { code: "off-study", label: "Off Study" },
  { code: "on-study", label: "On Study" },
  { code: "on-study-intervention", label: "On Study (Intervention)" },
  { code: "on-study-observation", label: "On Study (Observation)" },
  { code: "pending-on-study", label: "Pending On Study" },
  { code: "potential-candidate", label: "Potential Candidate" },
  { code: "screening", label: "Screening" },
  { code: "withdrawn", label: "Withdrawn" },
];

interface SubjectStateControlProps {
  currentState: string | null;
  busy: boolean;
  onUpdate: (state: string) => void;
}

export default function SubjectStateControl({
  currentState,
  busy,
  onUpdate,
}: SubjectStateControlProps) {
  const [state, setState] = useState("");

  return (
    <section className="card" aria-label="Subject state">
      <p className="section-title">Subject state</p>
      <p className="status-note">Current state: {currentState ?? "none recorded yet"}</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!state) {
            return;
          }
          onUpdate(state);
          setState("");
        }}
      >
        <label className="form-field">
          New state
          <select value={state} onChange={(event) => setState(event.target.value)}>
            <option value="">Select a state</option>
            {STATE_OPTIONS.map((option) => (
              <option key={option.code} value={option.code}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn-secondary" disabled={busy || !state}>
          Update state
        </button>
      </form>
    </section>
  );
}
