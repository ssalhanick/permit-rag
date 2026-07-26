-- db/migrations/032_media_channels.sql
-- Media Curator H2-6 — channel-level curation (scale beyond per-video vetting).
-- ─────────────────────────────────────────────────────────
-- Vet a CHANNEL (the trust unit), then auto-enumerate its uploads and upsert a
-- media_refs row per video. Semantic links (H2-6.1) mean these videos surface with
-- no hand-assigned task_key, so a crawl is immediately useful. The Guardrail still
-- enforces youtube-only; per-video liveness/flagging is H2-3 (Freshness Watcher).
--
-- Additive/idempotent. `text + CHECK` (no enums). media_refs gains a nullable
-- channel_id so a crawled row is traceable to its source channel (NULL = hand-added).
--
-- Numbering: Media Curator took 030/031; this is 032. Phase 6 ontology/bids
-- cascades to 033.

CREATE TABLE IF NOT EXISTS media_channels (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id       text NOT NULL UNIQUE,          -- YouTube channel id (UC...)
    name             text NOT NULL,
    provider         text NOT NULL DEFAULT 'youtube',
    jurisdiction     text,                           -- null = national (applies everywhere)
    vetted_by        text,                           -- who approved this channel
    active           boolean NOT NULL DEFAULT true,
    last_crawled_at  timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT media_channels_provider_chk CHECK (provider IN ('youtube'))
);

CREATE INDEX IF NOT EXISTS idx_media_channels_active
    ON media_channels (channel_id) WHERE active;

-- Trace a crawled media_refs row back to its source channel (NULL = hand-added).
ALTER TABLE media_refs
    ADD COLUMN IF NOT EXISTS channel_id text;

COMMENT ON TABLE media_channels IS
    'Vetted YouTube channels for channel-level Media Curator ingest (H2-6). The '
    'trust unit is the channel; the crawler enumerates uploads via the free RSS '
    'feed and upserts one media_refs row per video.';
COMMENT ON COLUMN media_refs.channel_id IS
    'Source channel this row was crawled from (matches media_channels.channel_id); '
    'NULL for hand-added rows.';
