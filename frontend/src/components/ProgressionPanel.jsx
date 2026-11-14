import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { formatKm2, formatPercent } from "../format.js";
import {
  REASON_TITLE,
  directionText,
  formatDays,
  formatDelta,
  formatObserved,
  formatPctChange,
} from "../progression.js";
import ProgressionChart from "./ProgressionChart.jsx";

const DIRECTION_BADGE = { more: "danger", less: "success", similar: "secondary" };

function Series({ series }) {
  const { summary } = series;
  return (
    <div className="mb-3" data-testid={`series-${series.series_id}`}>
      <h3 className="h6 mb-1">
        Area {series.series_id}: {series.points.length} dates
      </h3>
      <ProgressionChart series={series} />

      <div className="table-responsive">
        <table className="table table-sm small align-middle mb-2">
          <thead>
            <tr>
              <th scope="col">Date taken</th>
              <th scope="col">Analysis</th>
              <th scope="col" className="text-end">
                Detected water (km²)
              </th>
              <th scope="col" className="text-end">
                Share of valid area
              </th>
              <th scope="col">Change since the previous date</th>
            </tr>
          </thead>
          <tbody>
            {series.points.map((p, i) => {
              const change = i === 0 ? null : series.changes[i - 1];
              return (
                <tr key={p.analysis_id}>
                  <td>{formatObserved(p.observed_at)}</td>
                  <td>
                    <Link to={`/analyses/${p.analysis_id}`}>Analysis {p.analysis_id}</Link>
                  </td>
                  <td className="text-end">{formatKm2(p.water_area_km2)}</td>
                  <td className="text-end">{formatPercent(p.water_pct_of_valid)}</td>
                  <td>
                    {change ? (
                      <>
                        <span className={`badge text-bg-${DIRECTION_BADGE[change.direction] || "light"} me-1`}>
                          {directionText(change.direction)}
                        </span>
                        {formatDelta(change.delta_km2)} ({formatPctChange(change.pct_change)}) in{" "}
                        {formatDays(change.days)}
                      </>
                    ) : (
                      <span className="text-muted">first date</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {summary.total_delta_km2 !== null && (
        <p className="small mb-1">
          From the first to the last date the detected water changed by {formatDelta(summary.total_delta_km2)}
          {summary.total_pct_change !== null && <> ({formatPctChange(summary.total_pct_change)})</>}. Most detected
          water: analysis {summary.peak_analysis_id}.
        </p>
      )}
      {series.warnings.map((w) => (
        <div key={w} className="alert alert-warning py-1 px-2 small mb-1" role="note">
          {w}
        </div>
      ))}
    </div>
  );
}

export default function ProgressionPanel({ eventId }) {
  const [state, setState] = useState({ status: "loading", data: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null });
    api
      .progression(eventId)
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch(() => !cancelled && setState({ status: "error", data: null }));
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  const { status, data } = state;
  return (
    <section className="card mt-3" aria-labelledby="progression-title">
      <div className="card-body">
        <h2 className="h6" id="progression-title">
          Change over time
        </h2>

        {status === "loading" && <p className="small text-muted mb-0">Loading…</p>}
        {status === "error" && (
          <p className="small text-muted mb-0">The comparison over time could not be loaded just now.</p>
        )}

        {status === "ready" && (
          <>
            {data.series.length === 0 ? (
              <p className="small text-muted">
                Nothing to compare yet. To see how the detected water changes, analyse images of the same area taken
                on different dates, and enter the date the satellite took each image when you upload it.
              </p>
            ) : (
              data.series.map((s) => <Series key={s.series_id} series={s} />)
            )}

            {data.unassigned.length > 0 && (
              <details className="small mb-2">
                <summary>
                  {data.unassigned.length} analys{data.unassigned.length === 1 ? "is is" : "es are"} not compared
                </summary>
                <ul className="mt-1 mb-0">
                  {data.unassigned.map((u) => (
                    <li key={u.analysis_id}>
                      <Link to={`/analyses/${u.analysis_id}`}>Analysis {u.analysis_id}</Link>
                      {u.original_filename && <> ({u.original_filename})</>}: {REASON_TITLE[u.reason] || u.reason}.{" "}
                      <span className="text-muted">{u.detail}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <p className="text-muted small mb-0">{data.note}</p>
          </>
        )}
      </div>
    </section>
  );
}
