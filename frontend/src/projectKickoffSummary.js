/**
 * projectKickoffSummary.js — format kickoff wizard fields for project detail display.
 */

/**
 * Join a string array for display, or return null when empty.
 *
 * @param {string[] | null | undefined} values
 * @returns {string | null}
 */
function joinLabels(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return null;
  }
  const labels = values.map((value) => String(value).trim()).filter(Boolean);
  return labels.length > 0 ? labels.join(", ") : null;
}

/**
 * Build display sections for kickoff wizard data stored on a project.
 *
 * @param {object | null | undefined} project
 * @returns {{
 *   hasKickoffData: boolean,
 *   address: string | null,
 *   spaces: string | null,
 *   workTypes: string | null,
 *   permits: string[],
 *   emptyMessage: string | null,
 * }}
 */
export function formatKickoffSummary(project) {
  if (!project) {
    return {
      hasKickoffData: false,
      address: null,
      spaces: null,
      workTypes: null,
      permits: [],
      emptyMessage: null,
    };
  }

  const address = project.address?.trim() || null;
  const spaces = joinLabels(project.spaces);
  const workTypes = joinLabels(project.work_types);
  const permits = Array.isArray(project.recommended_permits)
    ? project.recommended_permits.map((value) => String(value).trim()).filter(Boolean)
    : [];
  const hasKickoffData = Boolean(address || spaces || workTypes || permits.length > 0);

  return {
    hasKickoffData,
    address,
    spaces,
    workTypes,
    permits,
    emptyMessage: hasKickoffData
      ? null
      : "No kickoff details — project was created without the wizard.",
  };
}
