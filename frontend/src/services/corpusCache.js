/**
 * corpusCache.js — municipality-scoped on-device corpus chunk cache (Phase 3).
 */

const CACHE_KEY = "permit_rag_corpus_cache";

/**
 * Load cached corpus chunks from Preferences/localStorage.
 *
 * @returns {Promise<{ municipality: string, version: string, chunks: object[] } | null>}
 */
export async function loadCorpusCache() {
  const raw = localStorage.getItem(CACHE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Save corpus sync payload to device cache.
 *
 * @param {{ municipality: string, version: string, chunks: object[] }} payload
 */
export function saveCorpusCache(payload) {
  localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
}

/**
 * Simple cosine similarity for unit vectors (fallback when sqlite-vec unavailable).
 *
 * @param {number[]} a
 * @param {number[]} b
 * @returns {number}
 */
export function cosineSimilarity(a, b) {
  if (!a?.length || !b?.length || a.length !== b.length) {
    return 0;
  }
  let dot = 0;
  for (let i = 0; i < a.length; i += 1) {
    dot += a[i] * b[i];
  }
  return dot;
}

/**
 * Top-k search over cached chunks by query embedding.
 *
 * @param {object[]} chunks
 * @param {number[]} queryEmbedding
 * @param {number} topK
 * @returns {object[]}
 */
export function searchLocalCorpus(chunks, queryEmbedding, topK = 5) {
  const scored = chunks
    .map((chunk) => ({
      ...chunk,
      similarity: cosineSimilarity(chunk.embedding, queryEmbedding),
    }))
    .sort((x, y) => y.similarity - x.similarity);
  return scored.slice(0, topK);
}

/**
 * LRU eviction: drop municipality cache older than ttlMs.
 *
 * @param {object} cache
 * @param {number} ttlMs
 * @param {number} nowMs
 * @returns {boolean} true if cache was cleared
 */
export function evictStaleCorpusCache(cache, ttlMs, nowMs = Date.now()) {
  if (!cache?.cached_at) {
    return false;
  }
  const age = nowMs - Date.parse(cache.cached_at);
  if (age > ttlMs) {
    localStorage.removeItem(CACHE_KEY);
    return true;
  }
  return false;
}
