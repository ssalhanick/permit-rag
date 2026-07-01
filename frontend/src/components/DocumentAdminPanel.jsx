import React, { useEffect, useState } from "react";
import {
  fetchDocumentDetail,
  supersedeDocumentAdmin,
  updateDocumentAdmin,
} from "../api.js";
import {
  buildUpdatePayload,
  DOCUMENT_STATUS_OPTIONS,
  formatAdminError,
  validateSupersedePayload,
  validateUpdatePayload,
} from "../documentAdminUtils.js";

const DEFAULT_EDIT_FORM = {
  document_status: "",
  is_current: "",
  retrieval_weight: "",
  review_due: "",
};

const DEFAULT_SUPERSEDE_FORM = {
  replacement_doc_id: "",
  superseded_weight: "0.1",
};

/**
 * Admin panel for editing document governance metadata and supersession.
 */
export default function DocumentAdminPanel({
  docId,
  adminToken,
  candidateDocIds = [],
  onClose,
  onSaved,
}) {
  const [detail, setDetail] = useState(null);
  const [editForm, setEditForm] = useState(DEFAULT_EDIT_FORM);
  const [supersedeForm, setSupersedeForm] = useState(DEFAULT_SUPERSEDE_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [superseding, setSuperseding] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadDetail() {
      setLoading(true);
      setError("");
      try {
        const result = await fetchDocumentDetail(docId);
        if (cancelled) {
          return;
        }
        const doc = result.data;
        setDetail(doc);
        setEditForm({
          document_status: doc.document_status || "",
          is_current: doc.is_current ?? "",
          retrieval_weight: doc.retrieval_weight ?? "",
          review_due: doc.review_due ? String(doc.review_due).slice(0, 10) : "",
        });
      } catch (err) {
        if (!cancelled) {
          setError(formatAdminError(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [docId]);

  function handleEditChange(event) {
    const { name, value, type, checked } = event.target;
    setEditForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  }

  function handleSupersedeChange(event) {
    const { name, value } = event.target;
    setSupersedeForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSaveMetadata(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const payload = buildUpdatePayload(editForm);
    const validationErrors = validateUpdatePayload(payload);
    if (validationErrors.length) {
      setError(validationErrors.join(" "));
      return;
    }
    if (!adminToken.trim()) {
      setError("Enter X-Admin-Token before saving.");
      return;
    }
    setSaving(true);
    try {
      await updateDocumentAdmin(docId, payload, adminToken);
      setSuccess("Metadata updated.");
      onSaved?.();
    } catch (err) {
      setError(formatAdminError(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleSupersede(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const validationErrors = validateSupersedePayload(supersedeForm);
    if (validationErrors.length) {
      setError(validationErrors.join(" "));
      return;
    }
    if (!adminToken.trim()) {
      setError("Enter X-Admin-Token before superseding.");
      return;
    }
    const confirmed = window.confirm(
      `Supersede "${docId}" with "${supersedeForm.replacement_doc_id.trim()}"? ` +
        "Superseded documents are never deleted; retrieval weight is reduced."
    );
    if (!confirmed) {
      return;
    }
    setSuperseding(true);
    try {
      await supersedeDocumentAdmin(
        docId,
        {
          replacement_doc_id: supersedeForm.replacement_doc_id.trim(),
          superseded_weight: Number(supersedeForm.superseded_weight),
        },
        adminToken
      );
      setSuccess("Document superseded.");
      onSaved?.();
      onClose?.();
    } catch (err) {
      setError(formatAdminError(err));
    } finally {
      setSuperseding(false);
    }
  }

  return (
    <div className="doc-admin-overlay" onClick={onClose} role="presentation">
      <div
        className="panel doc-admin-panel doc-admin-modal"
        role="dialog"
        aria-labelledby="doc-admin-title"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
      <div className="doc-admin-header">
        <h2 id="doc-admin-title">Edit Document</h2>
        <button type="button" className="secondary-button" onClick={onClose}>
          Close
        </button>
      </div>

      {loading ? <p className="muted">Loading document…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success-box">{success}</p> : null}

      {detail ? (
        <>
          <div className="doc-admin-summary muted">
            <p>
              <strong>{detail.doc_id}</strong> · {detail.municipality} · {detail.doc_type}
            </p>
            <p>
              Chunks: {detail.chunk_count} · Superseded by: {detail.superseded_by || "—"}
            </p>
          </div>

          <form onSubmit={handleSaveMetadata} className="doc-admin-form">
            <h3>Metadata</h3>
            <div className="doc-filter-grid">
              <div>
                <label htmlFor="document_status">Status</label>
                <select
                  id="document_status"
                  name="document_status"
                  value={editForm.document_status}
                  onChange={handleEditChange}
                >
                  {DOCUMENT_STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="review_due">Review due</label>
                <input
                  id="review_due"
                  name="review_due"
                  type="date"
                  value={editForm.review_due || ""}
                  onChange={handleEditChange}
                />
              </div>
              <div>
                <label htmlFor="retrieval_weight">Retrieval weight (0–1)</label>
                <input
                  id="retrieval_weight"
                  name="retrieval_weight"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={editForm.retrieval_weight}
                  onChange={handleEditChange}
                />
              </div>
              <div className="doc-admin-checkbox">
                <label htmlFor="is_current">
                  <input
                    id="is_current"
                    name="is_current"
                    type="checkbox"
                    checked={Boolean(editForm.is_current)}
                    onChange={handleEditChange}
                  />
                  Is current for retrieval
                </label>
              </div>
            </div>
            <button type="submit" disabled={saving || !adminToken.trim()}>
              {saving ? "Saving…" : "Save metadata"}
            </button>
          </form>

          <form onSubmit={handleSupersede} className="doc-admin-form doc-admin-supersede">
            <h3>Supersede</h3>
            <p className="muted field-hint">
              Superseded documents are never deleted; retrieval weight is reduced.
            </p>
            <div className="doc-filter-grid">
              <div>
                <label htmlFor="replacement_doc_id">Replacement doc_id</label>
                {candidateDocIds.length ? (
                  <select
                    id="replacement_doc_id"
                    name="replacement_doc_id"
                    value={supersedeForm.replacement_doc_id}
                    onChange={handleSupersedeChange}
                  >
                    <option value="">— Select replacement —</option>
                    {candidateDocIds
                      .filter((id) => id !== docId)
                      .map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                  </select>
                ) : (
                  <input
                    id="replacement_doc_id"
                    name="replacement_doc_id"
                    value={supersedeForm.replacement_doc_id}
                    onChange={handleSupersedeChange}
                    placeholder="replacement-doc-id"
                  />
                )}
              </div>
              <div>
                <label htmlFor="superseded_weight">Superseded weight</label>
                <input
                  id="superseded_weight"
                  name="superseded_weight"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={supersedeForm.superseded_weight}
                  onChange={handleSupersedeChange}
                />
              </div>
            </div>
            <button type="submit" className="secondary-button" disabled={superseding || !adminToken.trim()}>
              {superseding ? "Superseding…" : "Supersede document"}
            </button>
          </form>
        </>
      ) : null}
      </div>
    </div>
  );
}
