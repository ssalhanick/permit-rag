import test from "node:test";
import assert from "node:assert/strict";
import { isPushNotificationsEnabled } from "./pushNotifications.js";

test("isPushNotificationsEnabled is false unless env flag is true", () => {
  assert.equal(isPushNotificationsEnabled(), false);
});
