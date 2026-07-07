import type { NextStep } from "../../api/types";

interface TimelineProps {
  completed: string[];
  current: string[];
  nextSteps: NextStep[];
  titles?: Record<string, string>;
}

export default function Timeline({ completed, current, nextSteps, titles }: TimelineProps) {
  const label = (actionId: string) => titles?.[actionId] ?? actionId;

  return (
    <nav aria-label="Study timeline" className="timeline">
      <h2 className="section-title">Study timeline</h2>
      <ol>
        {completed.map((actionId) => (
          <li key={actionId} className="timeline-node done">
            {label(actionId)}
          </li>
        ))}
        {current.map((actionId) => (
          <li key={actionId} className="timeline-node active">
            {label(actionId)}
          </li>
        ))}
        {nextSteps.map((step) => (
          <li key={step.actionId} className="timeline-node upcoming">
            {step.title}
          </li>
        ))}
      </ol>
    </nav>
  );
}
