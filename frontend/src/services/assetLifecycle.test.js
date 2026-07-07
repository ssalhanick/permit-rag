import test from "node:test";
import assert from "node:assert/strict";
import {
  ASSET_STATES,
  classifyAssetSize,
  isEvictable,
  SIZE_CLASS,
  sweepEvictions,
  transitionAfterCloudAck,
} from "./assetLifecycle.js";

test("classifyAssetSize buckets", () => {
  assert.equal(classifyAssetSize(1024), SIZE_CLASS.HOT_SMALL);
  assert.equal(classifyAssetSize(10 * 1024 * 1024), SIZE_CLASS.HOT_LARGE);
  assert.equal(classifyAssetSize(60 * 1024 * 1024), SIZE_CLASS.COLD_LARGE);
});

test("transitionAfterCloudAck moves uploading to cloud_primary", () => {
  assert.equal(
    transitionAfterCloudAck(ASSET_STATES.UPLOADING, { checksum: "abc" }),
    ASSET_STATES.CLOUD_PRIMARY,
  );
});

test("isEvictable respects pin and size class", () => {
  const old = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString();
  assert.equal(
    isEvictable({
      sync_state: ASSET_STATES.EVICTABLE,
      size_class: SIZE_CLASS.HOT_SMALL,
      last_access_at: old,
      pinned: true,
    }),
    false,
  );
  assert.equal(
    isEvictable({
      sync_state: ASSET_STATES.EVICTABLE,
      size_class: SIZE_CLASS.COLD_LARGE,
      last_access_at: old,
    }),
    false,
  );
});

test("sweepEvictions evicts idle small PDFs", () => {
  const old = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString();
  const out = sweepEvictions([
    {
      asset_id: "a1",
      sync_state: ASSET_STATES.CLOUD_PRIMARY,
      size_class: SIZE_CLASS.HOT_SMALL,
      last_access_at: old,
      local_path: "/data/a1.pdf",
    },
  ]);
  assert.equal(out[0].sync_state, ASSET_STATES.LOCAL_EVICTED);
  assert.equal(out[0].local_path, null);
});
