/**
 * projectKickoffRoutes.js — kickoff deep links and wizard prefill helpers.
 */

import { SPACE_OPTIONS, WORK_TYPE_OPTIONS } from "./projectPermitRules.js";

const ALL_SPACE_OPTIONS = [...SPACE_OPTIONS.indoor, ...SPACE_OPTIONS.outdoor];

/**
 * Build a kickoff wizard URL with optional project edit context.
 *
 * @param {{ mode?: "landing" | "wizard" | "basic", projectId?: string, returnTo?: string }} opts
 * @returns {string}
 */
export function buildKickoffPath(opts = {}) {
  const params = new URLSearchParams();
  if (opts.mode && opts.mode !== "landing") {
    params.set("mode", opts.mode);
  }
  if (opts.projectId) {
    params.set("projectId", opts.projectId);
  }
  if (opts.returnTo) {
    params.set("returnTo", opts.returnTo);
  }
  const query = params.toString();
  return query ? `/kickoff?${query}` : "/kickoff";
}

/**
 * Split stored labels into known checkbox values and free-text "other".
 *
 * @param {string[] | null | undefined} values
 * @param {string[]} knownOptions
 * @returns {{ known: string[], other: string }}
 */
export function splitKnownAndOther(values, knownOptions) {
  const labels = Array.isArray(values) ? values.map((v) => String(v).trim()).filter(Boolean) : [];
  const known = labels.filter((label) => knownOptions.includes(label));
  const other = labels.filter((label) => !knownOptions.includes(label)).join(", ");
  return { known, other };
}

/**
 * Map a persisted project into wizard form state.
 *
 * @param {object | null | undefined} project
 * @returns {object}
 */
export function projectToWizardState(project) {
  if (!project) {
    return {
      address: "",
      municipality: null,
      name: "",
      spaces: [],
      otherSpaces: "",
      workTypes: [],
      otherWorkTypes: "",
    };
  }

  const { known: spaces, other: otherSpaces } = splitKnownAndOther(project.spaces, ALL_SPACE_OPTIONS);
  const { known: workTypes, other: otherWorkTypes } = splitKnownAndOther(
    project.work_types,
    WORK_TYPE_OPTIONS,
  );

  return {
    address: project.address?.trim() || "",
    municipality: project.municipality || null,
    name: project.name?.trim() || "",
    spaces,
    otherSpaces,
    workTypes,
    otherWorkTypes,
  };
}
