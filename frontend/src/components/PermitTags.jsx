/**
 * PermitTags — pill tags for recommended permit categories.
 */

import React from "react";

/**
 * @param {{ permits: string[] }} props
 */
export default function PermitTags({ permits }) {
  if (!permits || permits.length === 0) {
    return null;
  }

  return (
    <div className="kickoff-permit-tags" role="list" aria-label="Recommended permits">
      {permits.map((permit) => (
        <span key={permit} className="kickoff-permit-tag" role="listitem">
          {permit}
        </span>
      ))}
    </div>
  );
}
