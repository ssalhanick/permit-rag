import test from "node:test";
import assert from "node:assert/strict";

import { formatKickoffSummary } from "./projectKickoffSummary.js";

test("formatKickoffSummary returns empty state for missing project", () => {
  const summary = formatKickoffSummary(null);
  assert.equal(summary.hasKickoffData, false);
  assert.equal(summary.emptyMessage, null);
});

test("formatKickoffSummary returns empty message when no kickoff fields exist", () => {
  const summary = formatKickoffSummary({ name: "Pool", description: "Backyard remodel" });
  assert.equal(summary.hasKickoffData, false);
  assert.match(summary.emptyMessage, /without the wizard/);
});

test("formatKickoffSummary formats partial kickoff data", () => {
  const summary = formatKickoffSummary({
    address: "123 Main St, Dallas, TX",
    spaces: [],
    work_types: null,
    recommended_permits: [],
  });
  assert.equal(summary.hasKickoffData, true);
  assert.equal(summary.address, "123 Main St, Dallas, TX");
  assert.equal(summary.spaces, null);
  assert.equal(summary.workTypes, null);
  assert.deepEqual(summary.permits, []);
  assert.equal(summary.emptyMessage, null);
});

test("formatKickoffSummary formats full kickoff data", () => {
  const summary = formatKickoffSummary({
    address: "456 Oak Ave, Plano, TX",
    spaces: ["Kitchen", "Roof"],
    work_types: ["Electrical", "Plumbing"],
    recommended_permits: ["Electrical", "Plumbing"],
  });
  assert.equal(summary.hasKickoffData, true);
  assert.equal(summary.spaces, "Kitchen, Roof");
  assert.equal(summary.workTypes, "Electrical, Plumbing");
  assert.deepEqual(summary.permits, ["Electrical", "Plumbing"]);
});
