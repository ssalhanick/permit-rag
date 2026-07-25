import React, { useCallback, useEffect, useState } from "react";
import { listCorpusDocuments } from "../api.js";

/**
 * Read-only corpus metadata view (superadmin). Shows every document's stored
 * metadata straight from the DB — the corpus's source of truth — so gaps like a
 * null effective_date or a missing checksum are visible on the site. Review and
 * editing live in the Metadata Review tab; this is look-only.
 */
export default function DocumentMetadataTable() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listCorpusDocuments();
      setDocs(res.data?.documents || []);
    } catch (err) {
      setError(err.message || "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <p>Loading…</p>;

  const missingDates = docs.filter((d) => !d.effective_date).length;
  const missingChecksums = docs.filter((d) => !d.checksum_sha256).length;

  return (
    <div>
      <div style={S.toolbar}>
        <button type="button" style={S.btnGhost} onClick={load}>Refresh</button>
        <span style={S.muted}>{docs.length} document(s)</span>
        {missingDates > 0 && <span style={S.warn}>{missingDates} missing effective_date</span>}
        {missingChecksums > 0 && <span style={S.warn}>{missingChecksums} missing checksum</span>}
      </div>
      {error && <p style={S.error}>{error}</p>}
      <div style={{ overflowX: "auto" }}>
        <table style={S.table}>
          <thead>
            <tr>
              {["doc_id", "municipality", "doc_type", "authority", "effective_date",
                "status", "subject_tags", "checksum", "review_due", "tier"].map((h) => (
                <th key={h} style={S.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id || d.doc_id}>
                <td style={S.tdStrong} title={d.source_url}>{d.doc_id}</td>
                <td style={S.td}>{d.municipality}</td>
                <td style={S.td}>{d.doc_type}</td>
                <td style={S.td}>{d.authority_level}</td>
                <td style={d.effective_date ? S.td : S.tdMissing}>
                  {d.effective_date || "— missing"}
                </td>
                <td style={d.document_status === "draft" ? S.tdWarn : S.td}>
                  {d.document_status}
                </td>
                <td style={S.td}>{(d.subject_tags || []).join(", ") || "—"}</td>
                <td style={d.checksum_sha256 ? S.td : S.tdMissing}>
                  {d.checksum_sha256 ? `${String(d.checksum_sha256).slice(0, 10)}…` : "— missing"}
                </td>
                <td style={S.td}>{d.review_due || "—"}</td>
                <td style={S.td}>{d.source_tier}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const BORDER = "1px solid rgba(148,163,184,0.35)";
const S = {
  toolbar: { display: "flex", gap: "0.75rem", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap" },
  muted: { color: "#94a3b8", fontSize: "0.85rem" },
  warn: { color: "#d9822b", fontSize: "0.85rem" },
  error: { color: "#ef4444" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" },
  th: { textAlign: "left", color: "#94a3b8", fontWeight: 500, padding: "6px 10px", borderBottom: BORDER, whiteSpace: "nowrap" },
  td: { padding: "8px 10px", borderBottom: BORDER, verticalAlign: "top" },
  tdStrong: { padding: "8px 10px", borderBottom: BORDER, verticalAlign: "top", fontWeight: 600, wordBreak: "break-all" },
  tdMissing: { padding: "8px 10px", borderBottom: BORDER, verticalAlign: "top", color: "#ef4444" },
  tdWarn: { padding: "8px 10px", borderBottom: BORDER, verticalAlign: "top", color: "#d9822b", fontWeight: 600 },
};
