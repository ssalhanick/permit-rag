import test from "node:test";
import assert from "node:assert/strict";

import { fetchDocuments, fetchDocumentStatus, requestJson } from "./api.js";

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

  assert.ok(calledUrl.includes("/api/documents?"));
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
  assert.ok(calledUrl.includes("/api/documents/status?municipality=plano"));
});

test("requestJson rejects HTML body masquerading as success", async () => {
  global.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => "text/html" },
    text: async () => "<!doctype html><html><body>SPA</body></html>",
  });

  await assert.rejects(
    () => requestJson("/query/answer", { method: "POST", body: { query: "test" } }),
    /web page instead of API data/,
  );
});

test("postDesignIntentByScan uses scan_id route", async () => {
  let calledUrl = "";
  global.fetch = async (url) => {
    calledUrl = String(url);
    return {
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          overlays: [],
          explanation: "ok",
          product_candidates: [],
          usage: { input_tokens: 0, output_tokens: 0, model: "rules" },
        }),
    };
  };

  const { postDesignIntentByScan } = await import("./api.js");
  await postDesignIntentByScan("proj-1", "scan-1", { utterance: "tile" });
  assert.ok(calledUrl.includes("/projects/proj-1/room-scans/scan-1/design-intent"));
});

test("postLibraryDesignIntent uses auth route", async () => {
  let calledUrl = "";
  global.fetch = async (url) => {
    calledUrl = String(url);
    return {
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          overlays: [],
          explanation: "ok",
          product_candidates: [],
          usage: { input_tokens: 0, output_tokens: 0, model: "rules" },
        }),
    };
  };

  const { postLibraryDesignIntent } = await import("./api.js");
  await postLibraryDesignIntent("scan-1", { utterance: "tile" });
  assert.ok(calledUrl.includes("/auth/me/room-scans/scan-1/design-intent"));
});

test("postRoomPreviewImage hits commerce route", async () => {
  let calledUrl = "";
  global.fetch = async (url) => {
    calledUrl = String(url);
    return {
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          image_base64: "aaa",
          mime_type: "image/png",
          provider: "mock",
          model: "mock-solid-png",
          prompt: "x",
          mock: true,
        }),
    };
  };

  const { postRoomPreviewImage } = await import("./api.js");
  await postRoomPreviewImage({ utterance: "tile", overlays: [] });
  assert.ok(calledUrl.includes("/commerce/room-preview-image"));
});
