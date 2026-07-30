/**
 * contractorNavConfig.js — sidebar nav for the contractor dashboard.
 */

/** @returns {{ label: string, path: string, end?: boolean }[]} */
export function getContractorNavItems() {
  return [
    { label: "Open Projects", path: "/contractor/dashboard", end: true },
    { label: "Licenses", path: "/contractor/licenses" },
  ];
}
