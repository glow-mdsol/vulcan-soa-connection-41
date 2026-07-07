import type { VisitDetail } from "../../api/types";

const PHASES = ["proposed", "planned", "ordered", "scheduled", "booked", "performing", "completed"] as const;

interface VisitCardProps {
  actionId: string;
  title?: string;
  detail: VisitDetail | undefined;
  busy?: boolean;
  onPlan: () => void;
  onOrder: () => void;
  onSchedule: () => void;
  onRespond: (participant: "patient" | "site") => void;
  onPerform: () => void;
  onCompleteTask: (taskId: string) => void;
  onCompleteVisit: () => void;
}

export default function VisitCard({
  actionId,
  title,
  detail,
  busy = false,
  onPlan,
  onOrder,
  onSchedule,
  onRespond,
  onPerform,
  onCompleteTask,
  onCompleteVisit,
}: VisitCardProps) {
  const phase = detail?.phase ?? "proposed";
  const phaseIndex = PHASES.indexOf(phase as (typeof PHASES)[number]);
  const participantStatus = (role: "patient" | "site") =>
    detail?.participants?.find((p) => p.role === role)?.status;

  return (
    <li aria-label={`Visit ${actionId}`} className="card">
      <div className="card-header">
        <strong className="card-title">{title ?? actionId}</strong>
        <span className="badge">{phase}</span>
      </div>
      {title && <div className="meta">{actionId}</div>}
      <ol aria-label="Visit phases" className="stepper">
        {PHASES.map((p, index) => (
          <li
            key={p}
            aria-current={p === phase ? "step" : undefined}
            className={phaseIndex > index ? "done" : undefined}
          >
            {p}
          </li>
        ))}
      </ol>

      {phase === "revoked" && <p className="chip">Revoked — subject withdrawn</p>}

      {phase === "proposed" && (
        <button className="btn" onClick={onPlan} disabled={busy}>
          Accept proposal
        </button>
      )}
      {phase === "planned" && (
        <button className="btn" onClick={onOrder} disabled={busy}>
          Authorize
        </button>
      )}
      {phase === "ordered" && (
        <button className="btn" onClick={onSchedule} disabled={busy}>
          Schedule
        </button>
      )}

      {phase === "scheduled" && (
        <div aria-label="Appointment responses" className="btn-row">
          <button
            className="btn"
            onClick={() => onRespond("patient")}
            disabled={busy || participantStatus("patient") === "accepted"}
          >
            Patient accepts
          </button>
          <button
            className="btn-secondary"
            onClick={() => onRespond("site")}
            disabled={busy || participantStatus("site") === "accepted"}
          >
            Site confirms
          </button>
        </div>
      )}

      {phase === "booked" && (
        <button className="btn" onClick={onPerform} disabled={busy}>
          Perform visit
        </button>
      )}

      {phase === "performing" && (
        <div>
          <ul aria-label="Visit tasks" className="task-list">
            {detail?.tasks?.map((task) => (
              <li key={task.id}>
                <span>
                  {task.description} — {task.status}
                </span>
                {task.status !== "completed" && task.status !== "cancelled" && (
                  <button
                    className="btn-secondary"
                    onClick={() => onCompleteTask(task.id)}
                    disabled={busy}
                  >
                    Done: {task.description}
                  </button>
                )}
              </li>
            ))}
          </ul>
          <button className="btn" onClick={onCompleteVisit} disabled={busy}>
            Complete visit
          </button>
        </div>
      )}
    </li>
  );
}
