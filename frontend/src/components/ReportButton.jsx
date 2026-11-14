import { useState } from "react";
import { api } from "../api/client.js";

/** Downloads the PDF report of an analysis. Anyone who is logged in may use it. */
export default function ReportButton({ analysisId }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleClick() {
    setBusy(true);
    setError("");
    try {
      const blob = await api.downloadReport(analysisId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `geoflood_analysis_${analysisId}_report.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button type="button" className="btn btn-outline-primary btn-sm" disabled={busy} onClick={handleClick}>
        {busy ? "Preparing the report…" : "Download report (PDF)"}
      </button>
      <span className="text-muted small ms-2">Uses the saved results: compute the impact first to include it.</span>
      {error && (
        <div className="alert alert-danger py-2 mt-2 mb-0" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
