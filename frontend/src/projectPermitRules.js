/**
 * projectPermitRules.js
 * Rule-based permit recommendation engine for the project kickoff wizard.
 * Maps selected work-type labels to permit categories.
 * Designed to be upgraded to an API call without changing callers.
 */

/** @type {Record<string, string[]>} */
const WORK_TYPE_TO_PERMITS = {
  "Plumbing":              ["Plumbing"],
  "Electrical":            ["Electrical"],
  "HVAC / Mechanical":     ["Mechanical"],
  "Structural / Framing":  ["Building"],
  "Roofing":               ["Building", "Roofing"],
  "Deck / Patio Build":    ["Building", "Zoning"],
  "Pool / Spa":            ["Building", "Zoning", "Electrical", "Plumbing"],
  "Demolition":            ["Building", "Demolition"],
  "Windows / Doors":       ["Building"],
  // Cosmetic work — no permit required
  "Paint / Drywall":       [],
  "Flooring":              [],
  "Tile / Backsplash":     [],
};

/**
 * Returns deduplicated permit categories required for the given work types.
 * Work types with no permit requirement are still accepted silently.
 *
 * @param {string[]} workTypes - Selected work-type labels from the wizard
 * @returns {string[]} Sorted, deduplicated permit category labels
 */
export function recommendPermits(workTypes) {
  if (!Array.isArray(workTypes) || workTypes.length === 0) return [];
  const seen = new Set();
  for (const wt of workTypes) {
    const permits = WORK_TYPE_TO_PERMITS[wt] ?? [];
    for (const p of permits) seen.add(p);
  }
  return [...seen].sort();
}

/**
 * Returns true if every selected work type is cosmetic (no permit needed).
 *
 * @param {string[]} workTypes
 * @returns {boolean}
 */
export function isCosmeticOnly(workTypes) {
  if (!Array.isArray(workTypes) || workTypes.length === 0) return false;
  return workTypes.every((wt) => {
    const permits = WORK_TYPE_TO_PERMITS[wt];
    return permits !== undefined && permits.length === 0;
  });
}

/** All supported work-type options for the wizard checkboxes. */
export const WORK_TYPE_OPTIONS = [
  "Paint / Drywall",
  "Flooring",
  "Tile / Backsplash",
  "Plumbing",
  "Electrical",
  "HVAC / Mechanical",
  "Structural / Framing",
  "Roofing",
  "Windows / Doors",
  "Deck / Patio Build",
  "Pool / Spa",
  "Demolition",
];

/** Indoor and outdoor space options for the wizard checkboxes. */
export const SPACE_OPTIONS = {
  indoor: [
    "Kitchen",
    "Bathroom",
    "Bedroom",
    "Living Room",
    "Basement",
    "Garage",
    "Attic",
    "Laundry Room",
  ],
  outdoor: [
    "Yard / Landscaping",
    "Roof",
    "Deck / Patio",
    "Pool / Spa",
    "Driveway",
    "Fence",
  ],
};
