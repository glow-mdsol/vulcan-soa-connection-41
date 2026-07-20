import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { getSoaGrid } from "../../api/client";
import type { SoaGridData } from "../../api/types";

function toCsv(grid: SoaGridData): string {
  const escape = (cell: string) => `"${cell.replace(/"/g, '""')}"`;
  const header = ["Activity", ...grid.visits.map((visit) => visit.title)];
  const rows = grid.activities.map((activity) => {
    const marked = new Set(grid.matrix[activity.id] ?? []);
    return [activity.label, ...grid.visits.map((visit) => (marked.has(visit.actionId) ? "X" : ""))];
  });
  return [header, ...rows].map((row) => row.map(escape).join(",")).join("\n");
}

export default function SoaGrid() {
  const { studyId } = useParams<{ studyId: string }>();
  const [searchParams] = useSearchParams();
  const planDefinitionId = searchParams.get("plan");

  const [grid, setGrid] = useState<SoaGridData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!studyId) {
      return;
    }
    let active = true;

    getSoaGrid(studyId, planDefinitionId)
      .then((result) => {
        if (active) {
          setGrid(result);
          setError(null);
        }
      })
      .catch(() => {
        if (active) {
          setError("Could not load the schedule of activities for this study.");
        }
      });

    return () => {
      active = false;
    };
  }, [studyId, planDefinitionId]);

  const visitIdsByActivity = useMemo(() => {
    const map = new Map<string, Set<string>>();
    if (!grid) {
      return map;
    }
    for (const [activityId, visitIds] of Object.entries(grid.matrix)) {
      map.set(activityId, new Set(visitIds));
    }
    return map;
  }, [grid]);

  function handlePrint() {
    window.print();
  }

  function handleDownloadCsv() {
    if (!grid) {
      return;
    }
    const blob = new Blob([toCsv(grid)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `soa-grid-${studyId ?? "study"}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (error) {
    return (
      <p role="alert" className="alert">
        {error}
      </p>
    );
  }

  if (!grid) {
    return <p className="status-note">Loading schedule of activities…</p>;
  }

  return (
    <div className="soa-grid-page">
      <div className="soa-grid-toolbar no-print">
        <h2 className="page-title">Schedule of Activities</h2>
        <div className="btn-row">
          <button type="button" className="btn-secondary" onClick={handlePrint}>
            Print
          </button>
          <button type="button" className="btn-secondary" onClick={handleDownloadCsv}>
            Download CSV
          </button>
        </div>
      </div>

      <div className="soa-grid-scroll">
        <table className="soa-grid-table" aria-label={`Schedule of activities for ${grid.label}`}>
          <thead>
            <tr>
              <th scope="col" className="soa-grid-corner">
                Activity
              </th>
              {grid.visits.map((visit) => (
                <th scope="col" key={visit.actionId}>
                  {visit.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.activities.map((activity) => (
              <tr key={activity.id}>
                <th scope="row">{activity.label}</th>
                {grid.visits.map((visit) => {
                  const marked = visitIdsByActivity.get(activity.id)?.has(visit.actionId) ?? false;
                  return (
                    <td key={visit.actionId} className="soa-grid-cell">
                      {marked && (
                        <span className="soa-grid-mark" aria-label="scheduled">
                          ●
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
