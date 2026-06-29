import test from "node:test";
import assert from "node:assert/strict";
import {
  getProfilePageTitle,
  PROFILE_NAV_ITEMS,
  PROFILE_PAGE_TITLES,
} from "./profileNavConfig.js";

test("profile nav includes dashboard and history routes", () => {
  const paths = PROFILE_NAV_ITEMS.map((item) => item.path);
  assert.ok(paths.includes("/profile/dashboard"));
  assert.ok(paths.includes("/profile/history"));
});

test("getProfilePageTitle returns mapped titles", () => {
  assert.equal(getProfilePageTitle("/profile/history"), PROFILE_PAGE_TITLES["/profile/history"]);
  assert.equal(getProfilePageTitle("/profile/unknown"), "Profile");
});
