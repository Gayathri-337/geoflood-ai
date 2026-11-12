import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { formatInt, formatKm2, formatPercent } from "../format.js";
import { LEVEL_BADGE, LEVEL_LABEL } from "../severity.js";

function valueText({ value, unit }) {
  if (value === null || value === undefined) return "not computed";
  if (unit === "%") return formatPercent(value);
  if (unit === "km") return `${formatKm2(value, 2)} km`;
  if (unit === "km²") return `${formatKm2(value, 3)} km²`;
  return formatInt(value);
}

function ruleText({ thresholds, unit }) {
  const suffix = unit === "%" ? "%" : unit ? ` ${unit}` : "";
  return ["moderate", "high", "severe"]
    .filter((level) => thresholds[level] !== null && thresholds[level] !== undefined)
    .map((level) => `${level} from ${thresholds[level]}${suffix}`)
    .join(", ");
}

function storedText(data) {
  if (!data.stored_severity) return "Not saved yet.";
  if (data.stored_severity === data.level) return "Saved.";
  return `The saved severity (${LEVEL_LABEL[data.stored_severity]}) is out of date. Save again to update it.`;
}

function LevelBadge({ level, testId, large }) {
  return (
    <span className={`badge text-bg-${LEVEL_BADGE[level] || "secondary"}${large ? " fs-6" : ""}`} data-testid={testId}>
      {LEVEL_LABEL[level] || level}
    </span>
  );
}

/** The severity of an analysis with the reasons. It loads on its own, so a failure here never breaks the page. */
export default function SeverityCard({ analysisId, canSave, refreshKey = 0, onSaved }) {
  const [state, setState] = useState({ status: "loading", data: null, error: "" });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .severity(analysisId)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data, error: "" });
      })
      .catch((err) => {
        if (!cancelled) setState({ status: "error", data: null, error: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, refreshKey]);

  async function handleSave() {
    setSaving(true);
    setSaveError("");
    try {
      const data = await api.saveSeverity(analysisId);
      setState({ status: "ready", data, error: "" });
      if (onSaved) onSaved(data.level);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const { status, data, error } = state;
  const reasons = data ? data.indicators.filter((i) => data.driven_by.includes(i.key)).map((i) => i.label) : [];

  return (
    <div className="card mb-3">
      <div className="card-body">
        <h2 className="h6">Severity (provisional rules)</h2>

        {status === "loading" && <p className="small text-muted mb-0">Loading…</p>}
        {status === "error" && <p className="small text-muted mb-0">Severity is unavailable: {error}</p>}

        {status === "ready" && (
          <>
            <div className="d-flex align-items-center gap-2 mb-1">
              <LevelBadge level={data.level} testId="severity-level" large />
              <span className="small text-muted" data-testid="severity-stored">
                {storedText(data)}
              </span>
            </div>
            {reasons.length > 0 && <p className="small mb-1">Decided by: {reasons.join("; ")}</p>}
            {!data.impact_included && (
              <p className="small mb-1">Impact has not been computed, so only the water area counts.</p>
            )}

            <table className="table table-sm small mb-2">
              <thead>
                <tr>
                  <th>Indicator</th>
                  <th className="text-end">Value</th>
                  <th>Level</th>
                </tr>
              </thead>
              <tbody>
                {data.indicators.map((indicator) => (
                  <tr key={indicator.key} className={data.driven_by.includes(indicator.key) ? "table-active fw-semibold" : ""}>
                    <td>
                      {indicator.label}
                      <div className="text-muted fw-normal">{ruleText(indicator)}</div>
                      {indicator.note && <div className="text-muted fw-normal">{indicator.note}</div>}
                    </td>
                    <td className="text-end">
                      {valueText(indicator)}
                      {indicator.detail && <div className="text-muted fw-normal">{indicator.detail}</div>}
                    </td>
                    <td>{indicator.level ? <LevelBadge level={indicator.level} /> : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {saveError && (
              <div className="alert alert-danger py-2" role="alert">
                {saveError}
              </div>
            )}
            {canSave ? (
              <button type="button" className="btn btn-outline-primary btn-sm" onClick={handleSave} disabled={saving}>
                {saving ? "Saving…" : "Save classification"}
              </button>
            ) : (
              <p className="small text-muted mb-0">Only analysts can save the classification.</p>
            )}
            <p className="text-muted small mt-2 mb-0">{data.note}</p>
          </>
        )}
      </div>
    </div>
  );
}