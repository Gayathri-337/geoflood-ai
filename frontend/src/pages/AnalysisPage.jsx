import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../auth/authContext.js";
import { formatDate, formatInt, formatKm2, formatLength, formatPercent } from "../format.js";
import AnalysisMap from "../map/AnalysisMap.jsx";
import { COLORS, IMPACT_LAYERS, LAYER_KEYS, LAYER_LABELS } from "../map/layers.js";

const MAX_NEAR_M = 10000;
const ANALYST_ROLES = new Set(["analyst", "admin"]);
const ALL_VISIBLE = Object.fromEntries(LAYER_KEYS.map((key) => [key, true]));

async function loadImpact(id) {
  const [summary, ...collections] = await Promise.all([
    api.impactSummary(id),
    ...IMPACT_LAYERS.map((layer) => api.impactLayer(id, layer)),
  ]);
  return { summary, layers: Object.fromEntries(IMPACT_LAYERS.map((layer, i) => [layer, collections[i]])) };
}

function Swatch({ color }) {
  return (
    <span
      className="d-inline-block rounded-1 me-2"
      style={{ width: 14, height: 14, background: color, verticalAlign: "-2px" }}
    />
  );
}

function layerDetail(key, collection, summary) {
  const count = collection?.features?.length ?? 0;
  if (key === "zones") return `${formatInt(count)} polygons`;
  if (!summary) return formatInt(count);
  if (key === "roads") {
    return `${formatInt(summary.roads.count)} (${formatLength(summary.roads.flooded_length_km)} flooded)`;
  }
  if (key === "farmland") {
    return `${formatInt(summary.farmland.count)} (${formatKm2(summary.farmland.flooded_area_km2, 3)} km² flooded)`;
  }
  const part = summary[key]; // villages or infrastructure
  return `${formatInt(part.count)} (${part.inside} inside, ${part.near} near)`;
}

export default function AnalysisPage() {
  const { analysisId } = useParams();
  const { user } = useAuth();
  const idValid = /^[1-9]\d{0,17}$/.test(analysisId || "");

  const [state, setState] = useState({
    status: "loading", analysis: null, zones: null, summary: null, layers: {}, version: 0, error: "",
  });
  const [visible, setVisible] = useState(ALL_VISIBLE);
  const [nearText, setNearText] = useState("500");
  const [computing, setComputing] = useState(false);
  const [computeError, setComputeError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!idValid) return undefined;
    let cancelled = false;
    setState((previous) => ({ ...previous, status: "loading", error: "" }));
    Promise.all([api.analysis(analysisId), api.zones(analysisId), loadImpact(analysisId)])
      .then(([analysis, zones, impact]) => {
        if (!cancelled) setState({ status: "ready", analysis, zones, ...impact, version: 1, error: "" });
      })
      .catch((err) => {
        if (!cancelled) {
          const message = err.status === 404 ? `Analysis ${analysisId} was not found.` : err.message;
          setState((previous) => ({ ...previous, status: "error", error: message }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, idValid, reloadKey]);

  async function handleCompute(event) {
    event.preventDefault();
    const near = Number(nearText);
    if (nearText.trim() === "" || !Number.isFinite(near) || near < 0 || near > MAX_NEAR_M) {
      setComputeError(`Enter a distance between 0 and ${MAX_NEAR_M} metres.`);
      return;
    }
    setComputing(true);
    setComputeError("");
    try {
      await api.computeImpact(analysisId, near);
      const impact = await loadImpact(analysisId);
      setState((previous) => ({ ...previous, ...impact, version: previous.version + 1 }));
    } catch (err) {
      setComputeError(err.message);
    } finally {
      setComputing(false);
    }
  }

  if (!idValid) {
    return (
      <div className="alert alert-warning" role="alert">
        &quot;{analysisId}&quot; is not a valid analysis number. <Link to="/">Back to the dashboard</Link>
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="alert alert-danger d-flex justify-content-between align-items-center" role="alert">
        <span>{state.error}</span>
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setReloadKey((k) => k + 1)}>
          Try again
        </button>
      </div>
    );
  }
  if (!state.analysis) {
    return (
      <div className="text-center text-muted py-5" role="status">
        Loading…
      </div>
    );
  }

  const { analysis: a, zones, summary, layers, version } = state;
  const hasBaseline = a.baseline_method !== "none";
  const canCompute = ANALYST_ROLES.has(user?.role);
  const mapLayers = { zones, ...layers };
  const zoneSwatches = hasBaseline
    ? [
        [COLORS.permanentWater, "Permanent water (on the baseline)"],
        [COLORS.newFlood, "New water vs baseline"],
      ]
    : [[COLORS.water, "Detected water (no baseline)"]];

  return (
    <>
      <nav className="mb-2">
        <Link to="/">← Dashboard</Link>
      </nav>
      <h1 className="h4 mb-1">
        Analysis {a.analysis_id}: {a.original_filename}
      </h1>
      <p className="text-muted small">
        Event {a.event_id} · created {formatDate(a.created_at)} · model {a.model_name} (threshold {a.threshold}) ·
        severity: {a.severity || "not classified yet"}
      </p>

      {a.warnings.length > 0 && (
        <div className="alert alert-warning py-2" role="alert">
          {a.warnings.map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      )}

      <div className="row g-3">
        <div className="col-lg-8">
          <div className="border rounded" style={{ height: "70vh", minHeight: 420 }}>
            <AnalysisMap
              key={a.analysis_id}
              bounds={a.bounds_wgs84}
              layers={mapLayers}
              visible={visible}
              version={version}
            />
          </div>
          <div className="text-muted small mt-1">
            Dashed rectangle: the analysed image. Base map and the village, road, farmland and facility data ©
            OpenStreetMap contributors.
          </div>
        </div>

        <div className="col-lg-4">
          <div className="card mb-3">
            <div className="card-body">
              <h2 className="h6">Detected water</h2>
              <dl className="row mb-0 small">
                <dt className="col-7">Surface water (rivers included)</dt>
                <dd className="col-5 text-end" data-testid="fig-water">
                  {formatKm2(a.water_area_km2)} km²
                </dd>
                <dt className="col-7">Share of the image</dt>
                <dd className="col-5 text-end">{formatPercent(a.water_pct_of_valid)}</dd>
                <dt className="col-7">On the baseline layer</dt>
                <dd className="col-5 text-end" data-testid="fig-permanent">
                  {hasBaseline ? `${formatKm2(a.permanent_water_area_km2)} km²` : "–"}
                </dd>
                <dt className="col-7">New water vs baseline</dt>
                <dd className="col-5 text-end" data-testid="fig-new">
                  {hasBaseline ? `${formatKm2(a.new_flood_area_km2)} km²` : "–"}
                </dd>
                <dt className="col-7">Average model confidence</dt>
                <dd className="col-5 text-end">
                  {a.mean_confidence === null ? "–" : formatPercent(a.mean_confidence * 100)}
                </dd>
              </dl>
              <p className="text-muted small mt-2 mb-0">
                {hasBaseline
                  ? "“New” is water that the baseline layer does not show. It is an approximation and also includes seasonal water."
                  : "No baseline layer was used, so permanent and new water are not separated."}{" "}
                Confidence is the model&apos;s average certainty, not an accuracy.
              </p>
            </div>
          </div>

          <div className="card mb-3">
            <div className="card-body">
              <h2 className="h6">Map layers</h2>
              {LAYER_KEYS.map((key) => (
                <div className="mb-2" key={key}>
                  <div className="form-check">
                    <input
                      className="form-check-input"
                      type="checkbox"
                      id={`layer-${key}`}
                      checked={visible[key]}
                      onChange={() => setVisible((previous) => ({ ...previous, [key]: !previous[key] }))}
                    />
                    <label className="form-check-label" htmlFor={`layer-${key}`}>
                      {key !== "zones" && <Swatch color={COLORS[key]} />}
                      {LAYER_LABELS[key]}
                      <span className="d-block text-muted small">{layerDetail(key, mapLayers[key], summary)}</span>
                    </label>
                  </div>
                  {key === "zones" && (
                    <div className="small text-muted ms-4">
                      {zoneSwatches.map(([color, label]) => (
                        <div key={label}>
                          <Swatch color={color} />
                          {label}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-body">
              <h2 className="h6">Impact</h2>
              <p className="small mb-1">Compared against: {summary.compared_against}.</p>
              <p className="small mb-2">
                Last computed: {summary.last_computed_at ? formatDate(summary.last_computed_at) : "not computed yet"}
              </p>
              {canCompute ? (
                <form onSubmit={handleCompute} className="d-flex gap-2 align-items-end">
                  <div>
                    <label htmlFor="near-m" className="form-label small mb-1">
                      &quot;Near&quot; distance (m)
                    </label>
                    <input
                      id="near-m"
                      type="number"
                      className="form-control form-control-sm"
                      min="0"
                      max={MAX_NEAR_M}
                      step="50"
                      value={nearText}
                      onChange={(e) => setNearText(e.target.value)}
                    />
                  </div>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={computing}>
                    {computing ? "Computing…" : "Compute impact"}
                  </button>
                </form>
              ) : (
                <p className="small text-muted mb-0">Computing impact needs the analyst role.</p>
              )}
              {computeError && (
                <div className="alert alert-danger py-2 mt-2 mb-0" role="alert">
                  {computeError}
                </div>
              )}
              <p className="text-muted small mt-2 mb-0">
                Only features mapped in OpenStreetMap are counted, so these numbers are lower bounds.
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
