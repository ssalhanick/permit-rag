import test from "node:test";
import assert from "node:assert/strict";
import { buildKickoffPath, projectToWizardState, splitKnownAndOther } from "./projectKickoffRoutes.js";

test("buildKickoffPath adds mode, projectId, and returnTo", () => {
  const path = buildKickoffPath({
    mode: "wizard",
    projectId: "abc-123",
    returnTo: "/projects",
  });
  assert.equal(path, "/kickoff?mode=wizard&projectId=abc-123&returnTo=%2Fprojects");
});

test("buildKickoffPath returns bare kickoff route by default", () => {
  assert.equal(buildKickoffPath(), "/kickoff");
});

test("splitKnownAndOther separates custom labels", () => {
  const result = splitKnownAndOther(["Kitchen", "Sunroom"], ["Kitchen", "Bathroom"]);
  assert.deepEqual(result.known, ["Kitchen"]);
  assert.equal(result.other, "Sunroom");
});

test("projectToWizardState maps persisted project fields", () => {
  const state = projectToWizardState({
    name: "Kitchen Remodel",
    address: "123 Main St",
    municipality: "dallas",
    spaces: ["Kitchen", "Pantry"],
    work_types: ["Plumbing", "Custom demo"],
  });
  assert.equal(state.name, "Kitchen Remodel");
  assert.deepEqual(state.spaces, ["Kitchen"]);
  assert.equal(state.otherSpaces, "Pantry");
  assert.deepEqual(state.workTypes, ["Plumbing"]);
  assert.equal(state.otherWorkTypes, "Custom demo");
});
