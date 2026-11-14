import { chartModel } from "../progression.js";
import { formatKm2 } from "../format.js";

/** A hand-drawn SVG line chart of the detected water area of one series (no chart library). */
export default function ProgressionChart({ series }) {
  const model = chartModel(series);
  if (!model) return <p className="small text-muted mb-2">Not enough water-area values to draw a chart.</p>;
  const { width, height, margin } = model;
  const description =
    `Detected water area in km² for ${model.points.length} dates, from ${model.xTicks[0].label} ` +
    `(${formatKm2(model.points[0].area)} km²) to ${model.xTicks[1].label} ` +
    `(${formatKm2(model.points[model.points.length - 1].area)} km²).`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={description}
      style={{ width: "100%", maxWidth: 560, height: "auto" }}
    >
      {model.yTicks.map((t) => (
        <g key={t.label + t.y}>
          <line x1={margin.left} x2={model.right} y1={t.y} y2={t.y} stroke="#dee2e6" strokeWidth="1" />
          <text x={margin.left - 6} y={t.y + 4} textAnchor="end" fontSize="11" fill="#6c757d">
            {t.label}
          </text>
        </g>
      ))}
      <line x1={margin.left} x2={model.right} y1={model.baselineY} y2={model.baselineY} stroke="#adb5bd" />
      <text x={12} y={margin.top + 4} fontSize="11" fill="#6c757d">
        km²
      </text>
      <path d={model.path} fill="none" stroke="#0d6efd" strokeWidth="2" />
      {model.points.map((p) => (
        <g key={p.analysis_id}>
          <circle cx={p.x} cy={p.y} r="4.5" fill="#0d6efd" stroke="#fff" strokeWidth="1.5">
            <title>{`${p.label}: ${formatKm2(p.area)} km² (analysis ${p.analysis_id})`}</title>
          </circle>
          <text x={p.x} y={p.y - 9} textAnchor="middle" fontSize="11" fill="#212529">
            {formatKm2(p.area, 1)}
          </text>
        </g>
      ))}
      {model.xTicks.map((t) => (
        <text key={t.label} x={t.x} y={height - 14} textAnchor={t.anchor} fontSize="11" fill="#6c757d">
          {t.label}
        </text>
      ))}
    </svg>
  );
}
