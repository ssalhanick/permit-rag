import React, { useEffect, useState } from "react";
import { fetchMaterialsEstimate } from "../api.js";

/**
 * Project materials BOM estimate panel (server-side from active room scan).
 */
export default function MaterialsEstimatePanel({ projectId }) {
  const [estimate, setEstimate] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchMaterialsEstimate(projectId);
        setEstimate(res.data);
      } catch (err) {
        setError(err.message || "Could not load materials estimate.");
      }
    })();
  }, [projectId]);

  if (error) {
    return <p className="muted">{error}</p>;
  }
  if (!estimate?.lines?.length) {
    return <p className="muted">Link a room scan and apply a design to see a materials estimate.</p>;
  }

  return (
    <div className="materials-estimate-panel">
      <ul className="materials-estimate-lines">
        {estimate.lines.map((line, idx) => (
          <li key={idx}>
            <strong>{line.product_title || line.overlay_type}</strong>
            {line.qty_estimate && (
              <span className="muted">
                {" "}
                — {line.qty_estimate.value} {line.qty_estimate.unit}
              </span>
            )}
            {line.line_estimate && (
              <span> · ${line.line_estimate.low}–${line.line_estimate.high}</span>
            )}
          </li>
        ))}
      </ul>
      {estimate.total_low != null && (
        <p>
          <strong>Estimated total:</strong> ${estimate.total_low}–${estimate.total_high}
        </p>
      )}
      <p className="muted">{estimate.disclaimer}</p>
    </div>
  );
}
