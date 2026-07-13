-- Room scan sync verification (Sprint 14)
-- Run against the same DB your mobile app uses (prod RDS when VITE_API_BASE_URL=permits.scottsalhanick.com).

-- 1) Column exists (migration 015)
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'projects'
  AND column_name = 'room_summary';

-- 2) Projects with synced derived summaries (no raw mesh)
SELECT id, name, room_summary->>'captured_at' AS captured_at, room_summary->'derived' AS derived
FROM projects
WHERE room_summary IS NOT NULL
ORDER BY room_summary->>'captured_at' DESC NULLS LAST;
