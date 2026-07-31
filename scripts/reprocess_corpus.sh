#!/usr/bin/env bash
# scripts/reprocess_corpus.sh — full corpus reprocess + RAGAs report
# ============================================================================
# Re-chunks every existing document (picking up any chunking-strategy change
# in ingestion/chunker.py -- e.g. the document-upload plan's static context
# prefix and structure-aware splitting), force re-embeds the result, then
# runs the RAGAs eval gate and writes a timestamped report.
#
# Why all three steps, in this order and not independently:
#   1. Re-chunking updates chunks.content (an upsert keyed on
#      document_id + chunk_index) but never touches the stored embedding.
#   2. Force re-embedding is therefore required afterward, or the new chunk
#      text just sits next to a stale vector computed from the old text.
#   3. Running RAGAs before both of the above complete would silently score
#      the OLD corpus and report "no change" -- not because nothing
#      improved, but because nothing was actually re-processed yet. See
#      README.md's "Corpus Reprocessing" section for the full explanation.
#
# Usage:
#   scripts/reprocess_corpus.sh --local
#   scripts/reprocess_corpus.sh --database-url='postgresql://...'
#
# A DB target flag is required -- there is no safe default. Every step
# prints its own target banner (scripts/_db_target.py); read it before
# trusting the run, especially against production.
#
# Fails gracefully: if any step fails, the script stops before the next
# one runs (re-embedding after a failed re-chunk, or scoring RAGAs after a
# failed re-embed, would waste the run on stale data and produce a
# misleading result) and always writes a report showing exactly how far it
# got. Exit code is 0 only when all three steps succeed.

set -uo pipefail

if [ ! -f "pyproject.toml" ]; then
  echo "Run this from the repo root (pyproject.toml not found in $(pwd))." >&2
  exit 2
fi

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 --local | --database-url='postgresql://...'" >&2
  echo "  A DB target flag is required -- there is no safe default." >&2
  exit 2
fi
DB_ARGS=("$@")

# Prefer an explicit override, then this repo's own venv (has ragas/
# sentence-transformers installed; a bare system python3 usually doesn't),
# then the Windows `py` launcher, then whatever python3 is on PATH.
if [ -n "${PY:-}" ]; then
  :
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif command -v py >/dev/null 2>&1; then
  PY="py"
else
  PY="python3"
fi

REPORT_DIR="evaluation/results"
mkdir -p "$REPORT_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$REPORT_DIR/reprocess_${TIMESTAMP}.log"
REPORT_FILE="$REPORT_DIR/reprocess_${TIMESTAMP}_report.txt"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

STEP1_STATUS="SKIPPED"
STEP2_STATUS="SKIPPED"
STEP3_STATUS="SKIPPED"

write_report() {
  {
    echo "Corpus reprocess report -- $TIMESTAMP"
    echo "Python: $PY"
    echo "DB target args: ${DB_ARGS[*]}"
    echo ""
    echo "Step 1 (re-chunk, scripts.ingest_documents --include-existing): $STEP1_STATUS"
    echo "Step 2 (force re-embed, ingestion.embedder --force):            $STEP2_STATUS"
    echo "Step 3 (RAGAs eval, --no-answer-cache --export):                $STEP3_STATUS"
    echo ""
    if [ -f "$LOG_FILE" ]; then
      echo "-- RAGAs summary (grepped from the full log) --"
      grep -A2 "^  AVG" "$LOG_FILE" 2>/dev/null || echo "(no RAGAs summary captured in this run -- see full log)"
      echo ""
      echo "Full log: $LOG_FILE"
    fi
  } | tee "$REPORT_FILE"
}

log "=== Corpus reprocess starting ==="
log "Python: $PY"
log "DB target args: ${DB_ARGS[*]}"

log "--- Step 1: re-chunk (scripts.ingest_documents --include-existing) ---"
if "$PY" -m scripts.ingest_documents --include-existing "${DB_ARGS[@]}" >>"$LOG_FILE" 2>&1; then
  STEP1_STATUS="OK"
  log "Step 1 OK"
else
  STEP1_STATUS="FAILED (exit $?)"
  log "Step 1 FAILED -- see $LOG_FILE."
  log "Stopping before re-embed: re-embedding stale chunking data would waste the run."
  write_report
  exit 1
fi

log "--- Step 2: force re-embed (ingestion.embedder --force) ---"
if "$PY" -m ingestion.embedder --force "${DB_ARGS[@]}" >>"$LOG_FILE" 2>&1; then
  STEP2_STATUS="OK"
  log "Step 2 OK"
else
  STEP2_STATUS="FAILED (exit $?)"
  log "Step 2 FAILED -- see $LOG_FILE."
  log "Stopping before RAGAs: scoring against stale embeddings would be a misleading comparison."
  write_report
  exit 1
fi

log "--- Step 3: RAGAs eval (--no-answer-cache --export) ---"
if "$PY" -m evaluation.ragas_eval --no-answer-cache --export "${DB_ARGS[@]}" >>"$LOG_FILE" 2>&1; then
  STEP3_STATUS="OK"
  log "Step 3 OK"
else
  STEP3_STATUS="FAILED (exit $?)"
  log "Step 3 FAILED -- see $LOG_FILE."
fi

write_report

if [ "$STEP3_STATUS" != "OK" ]; then
  log "=== Corpus reprocess finished with failures ==="
  exit 1
fi

log "=== Corpus reprocess complete -- all steps OK ==="
log "Report: $REPORT_FILE"
exit 0
