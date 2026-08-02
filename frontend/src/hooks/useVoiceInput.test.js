import test from "node:test";
import assert from "node:assert/strict";
import { friendlyMessage } from "./useVoiceInput.js";

test("friendlyMessage maps no-speech to a gentle retry prompt, not a raw code", () => {
  // Regression: RoomCaptureWeb.js used to emit two different strings for
  // this same condition ("no-speech" from onerror, "No speech detected"
  // from the onend fallback), and callers only ever checked one form -- so
  // the raw code leaked through as user-facing text about as often as it
  // was silently swallowed. Now there's exactly one code and one mapping.
  const message = friendlyMessage("no-speech");
  assert.equal(message, "Didn't catch that — try again.");
  assert.doesNotMatch(message, /no-speech/);
});

test("friendlyMessage maps both permission-denial spellings the same way", () => {
  assert.equal(friendlyMessage("not-allowed"), friendlyMessage("permission-denied"));
  assert.match(friendlyMessage("not-allowed"), /denied/i);
});

test("friendlyMessage maps network errors", () => {
  assert.match(friendlyMessage("network"), /internet connection/i);
});

test("friendlyMessage never produces the old self-contradictory wording", () => {
  // The bug: `Voice input not supported: ${err.message}` wrapped a normal
  // "didn't catch that" outcome in language implying the browser/feature
  // itself was unsupported. No mapped or fallback message should ever
  // combine "not supported" with a benign per-attempt failure code.
  for (const code of ["no-speech", "not-allowed", "permission-denied", "network", "some-unmapped-code"]) {
    assert.doesNotMatch(friendlyMessage(code), /not supported/i);
  }
});

test("friendlyMessage falls back to a labeled raw code for anything unmapped", () => {
  assert.equal(friendlyMessage("audio-capture"), "Voice input failed: audio-capture");
});
