
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { formatDate, formatInt, formatKm2 } from "../format.js";
import { LEVEL_BADGE, LEVEL_LABEL } from "../severity.js";

function Stat({ id, label, value, hint }) {
  return (
    <div className="col">
      <div className="card h-100 shadow-sm">
        <div className="card-body">
          <div className="text-muted small">{label}</div>
          <div className="fs-3 fw-semibold" data-testid={id}>
            {value}
          </div>
          {hint && <div className="text-muted small">{hint}</div>}
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [state, setState] = useState({
    status: "loading",
    stats: null,
    analyses: [],
    error: "",
  });

  const load = useCallback(async () => {
    setState((previous) => ({
      ...previous,
      status: "loading",
      error: "",
    }));

    try {
      const [stats, analyses] = await Promise.all([
        api.dashboard(),
        api.analyses(10),
      ]);

      setState({ status: "ready", stats, analyses, error: "" });
    } catch (err) {
      setState((previous) => ({
        ...previous,
        status: "error",
        error: err.message,
      }));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const { status, stats, analyses, error } = state;

  if (status === "error") {
    return (
      <div
        className="alert alert-danger d-flex justify-content-between align-items-center"
        role="alert"
      >
        <span>{error}</span>
        <button
          type="button"
          className="btn btn-sm btn-outline-danger"
          onClick={load}
        >
          Try again
        </button>
      </div>
    );
  }

  if (status === "loading" && !stats) {
    return (
      <div className="text-center text-muted py-5" role="status">
        Loading…
      </div>
    );
  }

  const hasBaseline = stats.analyses_with_baseline > 0;

  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h4 mb-0">Dashboard</h1>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          onClick={load}
          disabled={status === "loading"}
        >
          Refresh
        </button>
      </div>

      <div className="row row-cols-2 row-cols-md-4 g-3 mb-3">
        <Stat
          id="stat-events"
          label="Events"
          value={formatInt(stats.events)}
        />
        <Stat
          id="stat-images"
          label="Images"
          value={formatInt(stats.images)}
        />
        <Stat
          id="stat-analyses"
          label="Analyses completed"
          value={formatInt(stats.analyses_completed)}
        />
        <Stat
          id="stat-polygons"
          label="Water polygons"
          value={formatInt(stats.zone_polygons)}
        />
      </div>

      <div className="row row-cols-1 row-cols-md-3 g-3 mb-2">
        <Stat
          id="stat-water"
          label="Detected surface water (km²)"
          value={formatKm2(stats.total_water_area_km2)}
          hint="rivers and lakes included"
        />
        <Stat
          id="stat-permanent"
          label="On the baseline layer (km²)"
          value={
            hasBaseline
              ? formatKm2(stats.total_permanent_water_area_km2)
              : "–"
          }
          hint="water that the baseline already shows"
        />
        <Stat
          id="stat-new"
          label="New water vs baseline (km²)"
          value={
            hasBaseline
              ? formatKm2(stats.total_new_flood_area_km2)
              : "–"
          }
          hint="an approximation: includes seasonal water"
        />
      </div>

      <p className="text-muted small mb-4">
        {stats.note} Latest analysis: {formatDate(stats.latest_analysis_at)}.
      </p>

      <h2 className="h5">Recent analyses</h2>

      {analyses.length === 0 ? (
        <p className="text-muted">No analyses yet.</p>
      ) : (
        <div className="table-responsive">
          <table className="table table-sm table-hover align-middle">
            <thead>
              <tr>
                <th>ID</th>
                <th>Image</th>
                <th>Event</th>
                <th className="text-end">Water (km²)</th>
                <th className="text-end">New vs baseline (km²)</th>
                <th className="text-end">Polygons</th>
                <th>Severity</th>
                <th>Created</th>
              </tr>
            </thead>

            <tbody>
              {analyses.map((a) => (
                <tr key={a.analysis_id}>
                  <td>
                    <Link to={`/analyses/${a.analysis_id}`}>
                      {a.analysis_id}
                    </Link>
                  </td>
                  <td>{a.original_filename}</td>
                  <td>{a.event_id}</td>
                  <td className="text-end">
                    {formatKm2(a.water_area_km2)}
                  </td>
                  <td className="text-end">
                    {a.baseline_method === "none" ? (
                      <span className="text-muted">no baseline</span>
                    ) : (
                      formatKm2(a.new_flood_area_km2)
                    )}
                  </td>
                  <td className="text-end">
                    {formatInt(a.zone_count)}
                  </td>
                  <td>
                    {a.severity ? (
                      <span
                        className={`badge text-bg-${
                          LEVEL_BADGE[a.severity] || "secondary"
                        }`}
                      >
                        {LEVEL_LABEL[a.severity] || a.severity}
                      </span>
                    ) : (
                      "–"
                    )}
                  </td>
                  <td>{formatDate(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
