/**
 * assetLifecycle.js — deterministic device asset sync/eviction state machine.
 */

export const ASSET_STATES = {
  LOCAL_ONLY: "local_only",
  UPLOADING: "uploading",
  CLOUD_PRIMARY: "cloud_primary",
  EVICTABLE: "evictable",
  LOCAL_EVICTED: "local_evicted",
};

export const SIZE_CLASS = {
  HOT_SMALL: "hot_small",
  HOT_LARGE: "hot_large",
  COLD_LARGE: "cold_large",
  METADATA: "metadata",
};

/** Default idle TTL before local eviction (ms). PDFs: 7 days. */
export const DEFAULT_PDF_IDLE_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * Classify file by size for lifecycle rules.
 *
 * @param {number} byteSize
 * @returns {string}
 */
export function classifyAssetSize(byteSize) {
  if (byteSize < 5 * 1024 * 1024) {
    return SIZE_CLASS.HOT_SMALL;
  }
  if (byteSize < 50 * 1024 * 1024) {
    return SIZE_CLASS.HOT_LARGE;
  }
  return SIZE_CLASS.COLD_LARGE;
}

/**
 * Transition asset state after cloud sync acknowledgement.
 *
 * @param {string} current
 * @param {{ checksum: string }} ack
 * @returns {string}
 */
export function transitionAfterCloudAck(current, ack) {
  if (!ack?.checksum) {
    return current;
  }
  if (current === ASSET_STATES.UPLOADING || current === ASSET_STATES.LOCAL_ONLY) {
    return ASSET_STATES.CLOUD_PRIMARY;
  }
  return current;
}

/**
 * Whether local blob may be evicted.
 *
 * @param {object} asset
 * @param {number} nowMs
 * @returns {boolean}
 */
export function isEvictable(asset, nowMs = Date.now()) {
  if (asset.pinned) {
    return false;
  }
  if (asset.size_class === SIZE_CLASS.COLD_LARGE || asset.size_class === SIZE_CLASS.HOT_LARGE) {
    return false;
  }
  if (asset.sync_state !== ASSET_STATES.CLOUD_PRIMARY && asset.sync_state !== ASSET_STATES.EVICTABLE) {
    return false;
  }
  const lastAccess = asset.last_access_at ? Date.parse(asset.last_access_at) : 0;
  const idleMs = asset.idle_ttl_ms ?? DEFAULT_PDF_IDLE_MS;
  return nowMs - lastAccess >= idleMs;
}

/**
 * Run eviction sweep over manifest entries.
 *
 * @param {object[]} manifest
 * @param {number} nowMs
 * @returns {object[]}
 */
export function sweepEvictions(manifest, nowMs = Date.now()) {
  return manifest.map((asset) => {
    if (!isEvictable(asset, nowMs)) {
      if (
        asset.sync_state === ASSET_STATES.CLOUD_PRIMARY &&
        isEvictable({ ...asset, sync_state: ASSET_STATES.EVICTABLE }, nowMs)
      ) {
        return { ...asset, sync_state: ASSET_STATES.EVICTABLE };
      }
      return asset;
    }
    return { ...asset, sync_state: ASSET_STATES.LOCAL_EVICTED, local_path: null };
  });
}
