import test from "node:test";
import assert from "node:assert/strict";
import { cosineSimilarity, searchLocalCorpus } from "./corpusCache.js";

test("cosineSimilarity identical vectors", () => {
  const v = [1, 0, 0];
  assert.ok(Math.abs(cosineSimilarity(v, v) - 1) < 0.001);
});

test("searchLocalCorpus returns top match", () => {
  const chunks = [
    { id: "1", doc_id: "a", chunk_index: 0, embedding: [1, 0] },
    { id: "2", doc_id: "b", chunk_index: 0, embedding: [0, 1] },
  ];
  const hits = searchLocalCorpus(chunks, [1, 0], 1);
  assert.equal(hits[0].id, "1");
});
