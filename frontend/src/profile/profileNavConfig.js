/** Sidebar and page title config for the user profile dashboard. */

export const PROFILE_NAV_ITEMS = [
  { label: "Dashboard", path: "/profile/dashboard", end: true },
  { label: "Query History", path: "/profile/history" },
  { label: "My Documents", path: "/profile/documents" },
  { label: "Account", path: "/profile/account" },
];

export const PROFILE_EXTERNAL_LINKS = [
  { label: "Projects", path: "/projects" },
  { label: "New Query", path: "/" },
];

/** @type {Record<string, string>} */
export const PROFILE_PAGE_TITLES = {
  "/profile/dashboard": "Dashboard",
  "/profile/history": "Query History",
  "/profile/documents": "My Documents",
  "/profile/account": "Account",
};

/**
 * Resolve the page title for a profile pathname.
 * @param {string} pathname
 * @returns {string}
 */
export function getProfilePageTitle(pathname) {
  return PROFILE_PAGE_TITLES[pathname] || "Profile";
}
