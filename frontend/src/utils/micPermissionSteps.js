/**
 * micPermissionSteps.js
 * Plain (non-JSX) module so this is unit-testable with node:test the same
 * way the rest of this codebase's utils are -- node's built-in test runner
 * can't parse JSX at all, even to reach a "pure" function, if it has to load
 * the whole file to get there. See MicPermissionHelp.jsx, which renders this.
 *
 * No browser exposes a URL a page can navigate to for its own per-origin
 * permission settings (blocked cross-browser for anti-abuse reasons), so
 * this is the click-path instead of the deep link that can't exist.
 */

export function detectBrowserSteps(ua = typeof navigator !== "undefined" ? navigator.userAgent : "") {
  if (/Edg\//.test(ua)) {
    return ["Click the lock icon in the address bar", "Set \"Microphone\" to \"Allow\"", "Reload the page"];
  }
  if (/Chrome\//.test(ua) && !/Edg\//.test(ua)) {
    return ["Click the lock icon in the address bar", "Set \"Microphone\" to \"Allow\"", "Reload the page"];
  }
  if (/Firefox\//.test(ua)) {
    return [
      "Click the lock icon in the address bar",
      "Clear the blocked microphone permission (click the × next to it)",
      "Reload the page and allow microphone access when prompted",
    ];
  }
  if (/Safari\//.test(ua) && !/Chrome\//.test(ua)) {
    return [
      "Open Safari → Settings → Websites → Microphone",
      "Find this site and set it to \"Allow\"",
      "Reload the page",
    ];
  }
  return [
    "Open your browser's site settings for this page",
    "Set \"Microphone\" to \"Allow\"",
    "Reload the page",
  ];
}
