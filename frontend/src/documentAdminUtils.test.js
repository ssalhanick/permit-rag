import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAdminHeaders,
  buildUpdatePayload,
  formatAdminError,
  validateSupersedePayload,
  validateUpdatePayload,
} from "./documentAdminUtils.js";

test("buildAdminHeaders includes token and role", () => {
  const headers = buildAdminHeaders("secret-token", "admin");
  assert.equal(headers["X-Admin-Token"], "secret-token");
  assert.equal(headers["X-Admin-Role"], "admin");
});

test("buildAdminHeaders returns empty object without token", () => {
  assert.deepEqual(buildAdminHeaders(""), {});
});

test("buildUpdatePayload strips empty fields", () => {
  const payload = buildUpdatePayload({
    document_status: "active",
    is_current: "",
    retrieval_weight: "",
    review_due: "",
  });
  assert.deepEqual(payload, { document_status: "active" });
});

test("buildUpdatePayload includes numeric and boolean fields", () => {
  const payload = buildUpdatePayload({
    document_status: "draft",
    is_current: true,
    retrieval_weight: "0.55",
    review_due: "2026-12-01",
  });
  assert.equal(payload.document_status, "draft");
  assert.equal(payload.is_current, true);
  assert.equal(payload.retrieval_weight, 0.55);
  assert.equal(payload.review_due, "2026-12-01");
});

test("validateUpdatePayload requires at least one field", () => {
  const errors = validateUpdatePayload({});
  assert.equal(errors.length, 1);
});

test("validateUpdatePayload rejects out-of-range retrieval weight", () => {
  const errors = validateUpdatePayload({ retrieval_weight: 1.5 });
  assert.match(errors[0], /between 0 and 1/);
});

test("validateSupersedePayload requires replacement doc_id", () => {
  const errors = validateSupersedePayload({ replacement_doc_id: "", superseded_weight: "0.1" });
  assert.match(errors[0], /replacement doc_id/i);
});

test("formatAdminError maps 403 to token message", () => {
  const err = new Error("Forbidden");
  err.meta = { status: 403 };
  assert.match(formatAdminError(err), /admin token/i);
});
