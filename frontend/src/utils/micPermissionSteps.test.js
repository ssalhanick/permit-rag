import test from "node:test";
import assert from "node:assert/strict";
import { detectBrowserSteps } from "./micPermissionSteps.js";

const CHROME_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const EDGE_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0";
const FIREFOX_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0";
const SAFARI_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15";

test("detectBrowserSteps gives the lock-icon path for Chrome", () => {
  const steps = detectBrowserSteps(CHROME_UA);
  assert.match(steps[0], /lock icon/i);
});

test("detectBrowserSteps still gives the lock-icon path for Edge, whose UA also contains 'Chrome/'", () => {
  // Edge's user agent string includes "Chrome/..." for compatibility -- the
  // Chrome branch's condition explicitly excludes it (&& !/Edg\//.test(ua))
  // so Edge doesn't fall through to the generic fallback by accident.
  const steps = detectBrowserSteps(EDGE_UA);
  assert.match(steps[0], /lock icon/i);
  assert.doesNotMatch(steps[0], /site settings/i); // would indicate the generic fallback fired instead
});

test("detectBrowserSteps gives Firefox its own permission-clearing path, not Chrome's", () => {
  const steps = detectBrowserSteps(FIREFOX_UA);
  assert.match(steps.join(" "), /firefox|blocked microphone permission/i);
});

test("detectBrowserSteps gives Safari its Settings > Websites path, not Chrome's lock icon", () => {
  const steps = detectBrowserSteps(SAFARI_UA);
  assert.match(steps[0], /Settings.*Websites.*Microphone/);
});

test("detectBrowserSteps falls back to generic guidance for an unrecognized UA", () => {
  const steps = detectBrowserSteps("SomeObscureBrowser/1.0");
  assert.ok(Array.isArray(steps) && steps.length > 0);
  assert.match(steps[0], /site settings/i);
});
