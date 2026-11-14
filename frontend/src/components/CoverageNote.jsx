import { useEffect, useState } from "react";
import { api } from "../api/client.js";

/**
 * Says how much reference data (OpenStreetMap) lies inside the analysed image, so that an impact of 0 is not
 * mistaken for "nothing affected". The wording comes from the server. If it cannot be loaded, nothing is shown
 * (the page's own "lower bounds" sentence stays).
 */
export default function CoverageNote({ analysisId }) {
  const [coverage, setCoverage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setCoverage(null);
    api
      .referenceCoverage(analysisId)
      .then((data) => !cancelled && setCoverage(data))
      .catch(() => !cancelled && setCoverage(null));
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  if (!coverage || !coverage.message) return null;
  if (coverage.level === "none" || coverage.level === "partial") {
    return (
      <div className="alert alert-warning py-2 small mb-2" role="note" data-testid="coverage-note">
        {coverage.message}
      </div>
    );
  }
  return (
    <p className="small text-muted mb-2" data-testid="coverage-note">
      {coverage.message}
    </p>
  );
}
