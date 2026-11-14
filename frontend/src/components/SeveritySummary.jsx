import { LEVEL_BADGE, LEVEL_LABEL } from "../severity.js";

const ORDER = ["severe", "high", "moderate", "low"];

/** How many analyses have each saved severity level. Shows nothing when the server sent no counts. */
export default function SeveritySummary({ counts }) {
  if (!counts || typeof counts !== "object") return null;
  const unclassified = Number(counts.not_classified) || 0;
  return (
    <div className="small mb-4 d-flex flex-wrap align-items-center gap-2" data-testid="severity-summary">
      <span className="text-muted">Saved severity levels (provisional rules):</span>
      {ORDER.map((level) => (
        <span key={level} className={`badge text-bg-${LEVEL_BADGE[level]}`}>
          {LEVEL_LABEL[level]} {Number(counts[level]) || 0}
        </span>
      ))}
      <span className="text-muted">Not classified yet: {unclassified}</span>
    </div>
  );
}
