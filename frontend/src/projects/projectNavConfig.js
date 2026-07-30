/**
 * projectNavConfig.js — sidebar nav for per-project dashboard.
 */

/**
 * @param {string} projectId
 * @returns {{ label: string, path: string, end?: boolean }[]}
 */
export function getProjectNavItems(projectId) {
  const base = `/projects/${projectId}`;
  return [
    { label: "Dashboard", path: `${base}/dashboard`, end: true },
    { label: "Room Scans", path: `${base}/scans` },
    { label: "Bidding", path: `${base}/bidding` },
    { label: "Query History", path: `${base}/queries` },
    { label: "Documents", path: `${base}/documents` },
    { label: "Members", path: `${base}/members` },
    { label: "Settings", path: `${base}/settings` },
  ];
}

/** @type {Record<string, string>} */
export const PROJECT_PAGE_TITLES = {
  dashboard: "Project Dashboard",
  scans: "Room Scans",
  bidding: "Bidding",
  queries: "Query History",
  documents: "Documents",
  members: "Members",
  settings: "Project Settings",
};

/**
 * @param {string} pathname
 * @returns {string}
 */
export function getProjectPageTitle(pathname) {
  const segment = pathname.split("/").pop() || "dashboard";
  return PROJECT_PAGE_TITLES[segment] || "Project";
}
