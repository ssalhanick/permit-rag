/**
 * ProjectKickoffSummary — renders persisted kickoff wizard fields on project detail.
 */

import PermitTags from "./PermitTags.jsx";
import { formatKickoffSummary } from "../projectKickoffSummary.js";

/**
 * @param {{ project: object | null | undefined }} props
 */
export default function ProjectKickoffSummary({ project }) {
  const summary = formatKickoffSummary(project);

  if (!summary.hasKickoffData) {
    if (!summary.emptyMessage) {
      return null;
    }
    return <p className="project-kickoff-empty muted">{summary.emptyMessage}</p>;
  }

  return (
    <section className="project-kickoff-summary" aria-label="Project kickoff details">
      <dl className="kickoff-summary">
        {summary.address && (
          <div className="kickoff-summary-row">
            <dt>Address</dt>
            <dd>{summary.address}</dd>
          </div>
        )}
        {summary.spaces && (
          <div className="kickoff-summary-row">
            <dt>Spaces</dt>
            <dd>{summary.spaces}</dd>
          </div>
        )}
        {summary.workTypes && (
          <div className="kickoff-summary-row">
            <dt>Work types</dt>
            <dd>{summary.workTypes}</dd>
          </div>
        )}
      </dl>

      {summary.permits.length > 0 && (
        <div className="kickoff-permit-section">
          <p className="kickoff-section-label">Likely permits needed</p>
          <PermitTags permits={summary.permits} />
        </div>
      )}
    </section>
  );
}
