import test from "node:test";
import assert from "node:assert/strict";

import { usernameFromEmail } from "./authUsername.js";

test("usernameFromEmail never returns an email format", () => {
  const username = usernameFromEmail("jane.doe@example.com");
  assert.ok(!username.includes("@"));
});

test("usernameFromEmail uses the sanitized local part plus suffix", () => {
  const username = usernameFromEmail("Jane.Doe+test@example.com", () => "abcd1234");
  assert.equal(username, "jane_doe_test_abcd1234");
});

test("usernameFromEmail keeps allowed characters", () => {
  const username = usernameFromEmail("build-crew_42@dfw.co", () => "ffff0000");
  assert.equal(username, "build-crew_42_ffff0000");
});

test("usernameFromEmail truncates very long local parts to 40 chars", () => {
  const long = "a".repeat(80) + "@example.com";
  const username = usernameFromEmail(long, () => "12345678");
  assert.equal(username, "a".repeat(40) + "_12345678");
});

test("usernameFromEmail falls back to 'user' for empty local part", () => {
  const username = usernameFromEmail("@example.com", () => "deadbeef");
  assert.equal(username, "user_deadbeef");
});

test("usernameFromEmail generates unique names across calls", () => {
  const a = usernameFromEmail("same@example.com");
  const b = usernameFromEmail("same@example.com");
  assert.notEqual(a, b);
});

test("usernameFromEmail default suffix is 8 hex chars", () => {
  const username = usernameFromEmail("x@y.com");
  const suffix = username.split("_").pop();
  assert.match(suffix, /^[0-9a-f]{8}$/);
});
