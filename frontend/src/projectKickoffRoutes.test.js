import test from "node:test";
import assert from "node:assert/strict";
import {
  buildKickoffPath,
  projectToWizardState,
  splitKnownAndOther,
  canonicalizeLabels,
  ALL_SPACE_OPTIONS,
} from "./projectKickoffRoutes.js";

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

test("projectToWizardState marks an existing project's name as manually-edited", () => {
  // A saved project's name is the user's own choice, not a stale
  // auto-suggestion -- the kickoff wizard's address-change re-derivation
  // must never overwrite it. See ProjectKickoffPage.jsx's name auto-populate
  // effects, keyed off this flag.
  const state = projectToWizardState({ name: "Kitchen Remodel", address: "123 Main St" });
  assert.equal(state.nameManuallyEdited, true);
});

test("projectToWizardState leaves a blank name free to auto-populate", () => {
  const state = projectToWizardState({ name: "", address: "123 Main St" });
  assert.equal(state.nameManuallyEdited, false);
});

test("canonicalizeLabels matches known options case-insensitively", () => {
  // Regression: the kickoff free-form extraction endpoint has no reason to
  // match the wizard's exact Title-Case option labels (e.g. "Kitchen") --
  // without this, an LLM-extracted "kitchen" would silently miss the
  // checkbox and land in free-text "other" instead.
  const result = canonicalizeLabels(["kitchen", "BATHROOM"], ["Kitchen", "Bathroom", "Bedroom"]);
  assert.deepEqual(result, ["Kitchen", "Bathroom"]);
});

test("canonicalizeLabels passes through anything with no case-insensitive match", () => {
  const result = canonicalizeLabels(["Sunroom"], ["Kitchen", "Bathroom"]);
  assert.deepEqual(result, ["Sunroom"]);
});

test("canonicalizeLabels feeds cleanly into splitKnownAndOther", () => {
  // The actual pipeline: canonicalize casing, then split known-vs-other.
  const canonical = canonicalizeLabels(["kitchen", "sunroom"], ALL_SPACE_OPTIONS);
  const { known, other } = splitKnownAndOther(canonical, ALL_SPACE_OPTIONS);
  assert.deepEqual(known, ["Kitchen"]);
  assert.equal(other, "sunroom");
});

test("ALL_SPACE_OPTIONS flattens both indoor and outdoor groups", () => {
  assert.ok(ALL_SPACE_OPTIONS.includes("Kitchen")); // indoor
  assert.ok(ALL_SPACE_OPTIONS.includes("Roof")); // outdoor
});
