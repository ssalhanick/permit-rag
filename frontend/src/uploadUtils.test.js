import test from "node:test";
import assert from "node:assert/strict";

import { formatUploadError, getUploadBlockers, suggestDocIdFromFilename } from "./uploadUtils.js";

test("suggestDocIdFromFilename normalizes filename", () => {
  const result = suggestDocIdFromFilename("Plano Pool Ordinance 2024.PDF");
  assert.equal(result, "plano-pool-ordinance-2024");
});

test("getUploadBlockers reports missing required fields", () => {
  const blockers = getUploadBlockers({
    file: null,
    docId: "",
    municipality: "",
    status: null,
  });
  assert.equal(blockers.length, 3);
});

test("formatUploadError maps auth issue", () => {
  const text = formatUploadError("Authentication required. Provide a valid admin token or log in as an admin.");
  assert.equal(text, "You need admin privileges for this action. Log in with an admin account.");
});
