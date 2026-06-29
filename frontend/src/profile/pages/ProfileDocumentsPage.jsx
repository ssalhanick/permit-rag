import React, { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../context/AuthContext.jsx";
import {
  fetchDocuments,
  fetchProjects,
  purgeDocumentAdmin,
  shareDocumentToProject,
} from "../../api.js";
import { formatAdminError, getStoredAdminToken } from "../../documentAdminUtils.js";

/**
 * User-uploaded documents with project share and admin purge actions.
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

  const userId = user?.id || user?.user_id;

  const loadDocuments = async () => {
    setLoading(true);
    setActionError("");
    try {
      const res = await fetchDocuments();
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

  const filteredDocs = useMemo(
    () => docs.filter((d) => user?.role === "admin" || d.uploaded_by === userId),
    [docs, user?.role, userId],
  );

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

  const handlePurgeDocument = async (docId) => {
    if (!window.confirm(`Are you sure you want to delete and purge all chunks for document ${docId}?`)) {
      return;
    }
    const adminToken = getStoredAdminToken();
    if (!adminToken.trim()) {
      setActionError("Set X-Admin-Token on Upload or Documents page before purging.");
      return;
    }
    try {
      await purgeDocumentAdmin(docId, adminToken, "admin", user?.username || userId || "");
      setActionSuccess(`Document ${docId} purged successfully.`);
      loadDocuments();
    } catch (err) {
      setActionError(`Failed to purge document: ${formatAdminError(err)}`);
    }
  };

  return (
    <section className="panel">
      <p className="muted">
        Manage and share your custom RAG ordinance and permit compliance documents.
      </p>

      {actionError && (
        <div className="profile-flash profile-flash--error">{actionError}</div>
      )}
      {actionSuccess && (
        <div className="profile-flash profile-flash--success">{actionSuccess}</div>
      )}

      {loading ? (
        <p>Loading documents...</p>
      ) : filteredDocs.length === 0 ? (
        <p className="muted">No uploaded documents found.</p>
      ) : (
        <div className="doc-table-wrap">
          <table className="profile-doc-table">
            <thead>
              <tr>
                <th>Doc ID</th>
                <th>Jurisdiction</th>
                <th>Type</th>
                <th>Uploaded by</th>
                <th>Status</th>
                <th>Copy to project</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredDocs.map((d) => (
                <tr key={d.id}>
                  <td>{d.doc_id}</td>
                  <td>{d.municipality}</td>
                  <td>{d.doc_type}</td>
                  <td>
                    {d.uploaded_by
                      ? d.uploaded_by === userId
                        ? "You"
                        : d.uploaded_by.slice(0, 8)
                      : "System"}
                  </td>
                  <td>
                    <span
                      className={`profile-doc-status profile-doc-status--${d.document_status}`}
                    >
                      {d.document_status}
                    </span>
                  </td>
                  <td>
                    <div className="profile-doc-share-row">
                      <select
                        value={targetProjectForDoc[d.id] || ""}
                        onChange={(e) =>
                          setTargetProjectForDoc((prev) => ({
                            ...prev,
                            [d.id]: e.target.value,
                          }))
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
                    <button
                      type="button"
                      className="secondary-button profile-btn-danger"
                      onClick={() => handlePurgeDocument(d.doc_id)}
                    >
                      Purge
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
