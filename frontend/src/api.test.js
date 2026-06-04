import test from "node:test";
import assert from "node:assert/strict";

import { fetchDocuments, fetchDocumentStatus } from "./api.js";

test("fetchDocuments sends query filters", async () => {
  let calledUrl = "";
  global.fetch = async (url) => {
    calledUrl = String(url);
    return {
      ok: true,
      status: 200,
      text: async () => "[]",
    };
  };

  await fetchDocuments({
    municipality: "Dallas",
    status: "active",
    authority: "municipal",
    doc_type: "zoning_ordinance",
  });

  assert.ok(calledUrl.includes("/documents?"));
  assert.ok(calledUrl.includes("municipality=dallas"));
  assert.ok(calledUrl.includes("status=active"));
  assert.ok(calledUrl.includes("authority=municipal"));
  assert.ok(calledUrl.includes("doc_type=zoning_ordinance"));
});

test("fetchDocumentStatus calls status endpoint", async () => {
  let calledUrl = "";
  global.fetch = async (url) => {
    calledUrl = String(url);
    return {
      ok: true,
      status: 200,
      text: async () => '{"counts":[]}',
    };
  };

  await fetchDocumentStatus({ municipality: "plano" });
  assert.ok(calledUrl.includes("/documents/status?municipality=plano"));
});
