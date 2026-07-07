import test from "node:test";
import assert from "node:assert/strict";

test("isNativePlatform is false without Capacitor window", async () => {
  const { isNativePlatform, isMapboxEnabled } = await import("./platform.js");
  assert.equal(isNativePlatform(), false);
  assert.equal(isMapboxEnabled(), true);
});

test("getOAuthRedirectUri uses web origin when not native", async () => {
  global.window = { location: { origin: "https://permits.scottsalhanick.com", protocol: "https:" } };
  global.Capacitor = undefined;
  const { getOAuthRedirectUri, isNativePlatform } = await import("./platform.js");
  assert.equal(isNativePlatform(), false);
  assert.equal(
    getOAuthRedirectUri(),
    "https://permits.scottsalhanick.com/auth/callback",
  );
});
