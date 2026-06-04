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
    adminToken: "",
    status: null,
  });
  assert.equal(blockers.length, 4);
});

test("formatUploadError maps auth issue", () => {
  const text = formatUploadError("Invalid or missing admin token.");
  assert.equal(text, "Auth failed. Check X-Admin-Token value.");
});
