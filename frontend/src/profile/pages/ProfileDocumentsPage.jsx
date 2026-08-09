import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import {
  deleteProjectDocument,
  downloadDocument,
  fetchDocuments,
  fetchProjects,
  replaceProjectDocument,
  shareDocumentToProject,
} from "../../api.js";
import { FileText, Plus, Download, RefreshCw, Trash2 } from "lucide-react";

const STATUS_BADGE = {
  draft: { label: "Pending review", className: "profile-doc-status--draft" },
  active: { label: "Active", className: "profile-doc-status--active" },
  superseded: { label: "Superseded", className: "profile-doc-status--superseded" },
  repealed: { label: "Repealed", className: "profile-doc-status--repealed" },
  needs_ocr: { label: "Processing", className: "profile-doc-status--needs_ocr" },
  rejected: { label: "Rejected", className: "profile-doc-status--rejected" },
};

/**
 * "Add Document" needs a project to upload into — the library itself is
 * cross-project. One project: go straight there. Multiple: pick one first.
 */
function AddDocumentCta({ userProjects }) {
  const navigate = useNavigate();
  const [projectId, setProjectId] = useState(userProjects[0]?.project_id || "");

  if (userProjects.length === 0) {
    return (
      <div className="profile-empty-state">
        <FileText className="profile-empty-state-icon" aria-hidden="true" />
        <p>You'll need a project before you can add a document.</p>
        <Link to="/kickoff" className="tt-btn-primary">
          Start a project
        </Link>
      </div>
    );
  }

  if (userProjects.length === 1) {
    return (
      <div className="profile-empty-state">
        <FileText className="profile-empty-state-icon" aria-hidden="true" />
        <p>No documents yet.</p>
        <button
          type="button"
          className="tt-btn-primary"
          onClick={() => navigate(`/projects/${userProjects[0].project_id}/documents/upload`)}
        >
          <Plus className="w-4 h-4" /> Add Document
        </button>
      </div>
    );
  }

  return (
    <div className="profile-empty-state">
      <FileText className="profile-empty-state-icon" aria-hidden="true" />
      <p>No documents yet.</p>
      <div className="profile-doc-share-row">
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
          {userProjects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="tt-btn-primary"
          disabled={!projectId}
          onClick={() => navigate(`/projects/${projectId}/documents/upload`)}
        >
          <Plus className="w-4 h-4" /> Add Document
        </button>
      </div>
    </div>
  );
}

/**
 * A user's own document library — their uploaded/petitioned/team-shared
 * documents only, never the full corpus (that's the superadmin-only /documents
 * corpus browser). See db_client.list_documents_for_user for the scoping rule.
 */
export default function ProfileDocumentsPage() {
  const { user } = useAuth();

  const [docs, setDocs] = useState([]);
  const [userProjects, setUserProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [targetProjectForDoc, setTargetProjectForDoc] = useState({});
  const [docShareFeedback, setDocShareFeedback] = useState({});
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const [busyDocId, setBusyDocId] = useState(null);
  const replaceInputRefs = useRef({});

  const userId = user?.id || user?.user_id;

  const loadDocuments = async () => {
    setLoading(true);
    setActionError("");
    try {
      const res = await fetchDocuments({ scope: "mine" });
      setDocs(res.data || []);
    } catch (err) {
      setActionError(`Failed to fetch documents: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const loadProjects = async () => {
    try {
      const res = await fetchProjects();
      setUserProjects(res.data || []);
    } catch (err) {
      console.warn("Failed to load user projects", err);
    }
  };

  useEffect(() => {
    if (user) {
      loadDocuments();
      loadProjects();
    }
  }, [user]);

  const ownsDoc = (d) => d.source_tier === 3 && d.uploaded_by === userId && d.project_id;

  const handleDownload = async (d) => {
    setActionError("");
    try {
      await downloadDocument(d.doc_id, d.doc_id);
    } catch (err) {
      setActionError(`Failed to download ${d.doc_id}: ${err.message}`);
    }
  };

  const handleDelete = async (d) => {
    if (!window.confirm(`Delete "${d.doc_id}"? This can't be undone.`)) return;
    setBusyDocId(d.id);
    setActionError("");
    try {
      await deleteProjectDocument(d.project_id, d.id);
      setActionSuccess(`Deleted ${d.doc_id}.`);
      await loadDocuments();
    } catch (err) {
      setActionError(`Failed to delete ${d.doc_id}: ${err.message}`);
    } finally {
      setBusyDocId(null);
    }
  };

  const handleReplaceFile = async (d, file) => {
    if (!file) return;
    setBusyDocId(d.id);
    setActionError("");
    try {
      await replaceProjectDocument(d.project_id, d.id, file);
      setActionSuccess(`Replacement for ${d.doc_id} uploaded — the old version is now marked superseded.`);
      await loadDocuments();
    } catch (err) {
      setActionError(`Failed to replace ${d.doc_id}: ${err.message}`);
    } finally {
      setBusyDocId(null);
    }
  };

  const handleShareDocToProject = async (docUuid) => {
    const projectId = targetProjectForDoc[docUuid];
    if (!projectId) {
      setDocShareFeedback((prev) => ({ ...prev, [docUuid]: "Please select a project." }));
      return;
    }
    try {
      await shareDocumentToProject(projectId, docUuid);
      const proj = userProjects.find((p) => p.project_id === projectId);
      setDocShareFeedback((prev) => ({
        ...prev,
        [docUuid]: `Copied successfully to ${proj ? proj.name : "project"}.`,
      }));
      setTimeout(() => {
        setDocShareFeedback((prev) => {
          const updated = { ...prev };
          delete updated[docUuid];
          return updated;
        });
      }, 4000);
    } catch (err) {
      setDocShareFeedback((prev) => ({ ...prev, [docUuid]: `Failed: ${err.message}` }));
    }
  };

  const sortedDocs = useMemo(
    () => [...docs].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1)),
    [docs],
  );

  return (
    <section className="panel">
      <p className="muted">Documents you've uploaded or petitioned, and anything shared with your project teams.</p>

      {actionError && <div className="profile-flash profile-flash--error">{actionError}</div>}
      {actionSuccess && <div className="profile-flash profile-flash--success">{actionSuccess}</div>}

      {loading ? (
        <p>Loading documents...</p>
      ) : sortedDocs.length === 0 ? (
        <AddDocumentCta userProjects={userProjects} />
      ) : (
        <>
          <div className="profile-doc-library-header">
            {userProjects.length > 0 && (
              <Link
                to={`/projects/${userProjects[0].project_id}/documents/upload`}
                className="tt-btn-primary text-xs"
              >
                <Plus className="w-3.5 h-3.5" /> Add Document
              </Link>
            )}
          </div>
          <div className="doc-table-wrap">
            <table className="profile-doc-table">
              <thead>
                <tr>
                  <th>Doc ID</th>
                  <th>Jurisdiction</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Copy to project</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedDocs.map((d) => {
                  const badge = STATUS_BADGE[d.document_status] || {
                    label: d.document_status,
                    className: "",
                  };
                  const canManage = ownsDoc(d);
                  const busy = busyDocId === d.id;
                  return (
                    <tr key={d.id}>
                      <td>{d.doc_id}</td>
                      <td>{d.municipality}</td>
                      <td>{d.doc_type}</td>
                      <td>
                        <span
                          className={`profile-doc-status ${badge.className}`}
                          title={d.document_status === "rejected" ? d.rejection_reason || "No reason given." : undefined}
                        >
                          {badge.label}
                        </span>
                        {d.document_status === "rejected" && d.rejection_reason && (
                          <div className="profile-doc-reject-reason">{d.rejection_reason}</div>
                        )}
                      </td>
                      <td>
                        <div className="profile-doc-share-row">
                          <select
                            value={targetProjectForDoc[d.id] || ""}
                            onChange={(e) =>
                              setTargetProjectForDoc((prev) => ({ ...prev, [d.id]: e.target.value }))
                            }
                          >
                            <option value="">Choose project</option>
                            {userProjects.map((p) => (
                              <option key={p.project_id} value={p.project_id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => handleShareDocToProject(d.id)}
                          >
                            Copy
                          </button>
                        </div>
                        {docShareFeedback[d.id] && (
                          <div className="profile-doc-share-feedback">{docShareFeedback[d.id]}</div>
                        )}
                      </td>
                      <td>
                        <div className="profile-doc-actions-row">
                          <button
                            type="button"
                            className="secondary-button"
                            title="View / download"
                            aria-label={`Download ${d.doc_id}`}
                            onClick={() => handleDownload(d)}
                          >
                            <Download className="w-3.5 h-3.5" />
                          </button>
                          {canManage && (
                            <>
                              <button
                                type="button"
                                className="secondary-button"
                                title="Replace / re-upload"
                                aria-label={`Replace ${d.doc_id}`}
                                disabled={busy}
                                onClick={() => replaceInputRefs.current[d.id]?.click()}
                              >
                                <RefreshCw className="w-3.5 h-3.5" />
                              </button>
                              <input
                                type="file"
                                className="hidden"
                                ref={(el) => (replaceInputRefs.current[d.id] = el)}
                                onChange={(e) => {
                                  const file = e.target.files?.[0];
                                  e.target.value = "";
                                  handleReplaceFile(d, file);
                                }}
                              />
                              <button
                                type="button"
                                className="secondary-button profile-btn-danger"
                                title="Delete"
                                aria-label={`Delete ${d.doc_id}`}
                                disabled={busy}
                                onClick={() => handleDelete(d)}
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
