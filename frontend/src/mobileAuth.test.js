import test from "node:test";
import assert from "node:assert/strict";

test("parseOAuthCallbackUrl extracts code from custom scheme", async () => {
  const { parseOAuthCallbackUrl } = await import("./mobileAuth.js");
  const result = parseOAuthCallbackUrl(
    "com.scottsalhanick.permitrag://auth/callback?code=abc123",
  );
  assert.equal(result.code, "abc123");
  assert.equal(result.error, null);
});

test("parseOAuthCallbackUrl extracts error", async () => {
  const { parseOAuthCallbackUrl } = await import("./mobileAuth.js");
  const result = parseOAuthCallbackUrl(
    "com.scottsalhanick.permitrag://auth/callback?error=access_denied",
  );
  assert.equal(result.code, null);
  assert.equal(result.error, "access_denied");
});
