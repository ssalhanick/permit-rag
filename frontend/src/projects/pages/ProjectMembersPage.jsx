import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  addProjectMember,
  deleteProject,
  fetchProjectMembers,
  removeProjectMember,
  transferProjectOwnership,
} from "../../api.js";
import { useAuth } from "../../context/AuthContext.jsx";
import { useProject } from "../ProjectContext.jsx";

/**
 * Collaborators and owner-only danger zone for a project.
 */
export default function ProjectMembersPage() {
  const { user } = useAuth();
  const { project, role, projectId } = useProject();
  const navigate = useNavigate();
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [newMemberForm, setNewMemberForm] = useState({ userId: "", role: "viewer" });
  const [transferOwnerId, setTransferOwnerId] = useState("");

  const isOwner = role === "owner";

  const refreshMembers = async () => {
    const res = await fetchProjectMembers(projectId);
    setMembers(res.data || []);
  };

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        await refreshMembers();
      } catch (err) {
        setError(err.message || "Failed to load members.");
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  const handleAddMember = async (e) => {
    e.preventDefault();
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await addProjectMember(projectId, newMemberForm.userId, newMemberForm.role);
      setSuccess("Member added.");
      setNewMemberForm({ userId: "", role: "viewer" });
      await refreshMembers();
    } catch (err) {
      setError(err.message || "Failed to add member.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveMember = async (userId, username) => {
    if (!window.confirm(`Remove "${username}" from this project?`)) {
      return;
    }
    setActionLoading(true);
    setError("");
    try {
      await removeProjectMember(projectId, userId);
      setSuccess("Collaborator removed.");
      await refreshMembers();
    } catch (err) {
      setError(err.message || "Failed to remove member.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleTransferOwnership = async (e) => {
    e.preventDefault();
    if (!window.confirm("Transfer ownership? You will lose owner controls.")) {
      return;
    }
    setActionLoading(true);
    setError("");
    try {
      await transferProjectOwnership(projectId, transferOwnerId);
      setSuccess("Ownership transferred.");
      setTransferOwnerId("");
    } catch (err) {
      setError(err.message || "Failed to transfer ownership.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!window.confirm(`Delete project "${project?.name}"? This cannot be undone.`)) {
      return;
    }
    setActionLoading(true);
    setError("");
    try {
      await deleteProject(projectId);
      navigate("/projects");
    } catch (err) {
      setError(err.message || "Failed to delete project.");
      setActionLoading(false);
    }
  };

  return (
    <div className="project-members-page">
      {error && <div className="error-box">{error}</div>}
      {success && <div className="success-box">{success}</div>}

      <section className="panel">
        <p className="muted">Your role: <strong>{role}</strong></p>

        {loading ? (
          <p>Loading collaborators…</p>
        ) : (
          <div className="doc-table-wrap">
            <table className="doc-table">
              <thead>
                <tr>
                  <th>Collaborator</th>
                  <th>Email</th>
                  <th>Role</th>
                  {isOwner && <th>Action</th>}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Creator (Owner)</strong></td>
                  <td>—</td>
                  <td><span className="badge badge-owner">Owner</span></td>
                  {isOwner && <td>—</td>}
                </tr>
                {members.map((m) => (
                  <tr key={m.user_id}>
                    <td>{m.username} {m.user_id === user?.id && "(You)"}</td>
                    <td>{m.email}</td>
                    <td><span className={`badge badge-${m.role}`}>{m.role}</span></td>
                    {isOwner && (
                      <td>
                        <button
                          type="button"
                          className="text-button delete-text"
                          onClick={() => handleRemoveMember(m.user_id, m.username)}
                          disabled={actionLoading}
                        >
                          Remove
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {isOwner && (
          <form onSubmit={handleAddMember} className="form inline-form project-add-member-form">
            <div>
              <label htmlFor="newMemberId">Add member (user UUID)</label>
              <input
                id="newMemberId"
                value={newMemberForm.userId}
                onChange={(e) => setNewMemberForm({ ...newMemberForm, userId: e.target.value })}
                placeholder="Paste user UUID"
                required
              />
            </div>
            <div>
              <label htmlFor="newMemberRole">Role</label>
              <select
                id="newMemberRole"
                value={newMemberForm.role}
                onChange={(e) => setNewMemberForm({ ...newMemberForm, role: e.target.value })}
              >
                <option value="viewer">viewer</option>
                <option value="editor">editor</option>
              </select>
            </div>
            <button type="submit" disabled={actionLoading} className="secondary-button">
              Add
            </button>
          </form>
        )}
      </section>

      {isOwner && (
        <section className="panel danger-zone">
          <h3>Danger zone</h3>

          <form onSubmit={handleTransferOwnership} className="form inline-form project-transfer-form">
            <div>
              <label htmlFor="transferId">Transfer ownership (new owner UUID)</label>
              <input
                id="transferId"
                value={transferOwnerId}
                onChange={(e) => setTransferOwnerId(e.target.value)}
                placeholder="Paste new owner's UUID"
                required
              />
            </div>
            <button type="submit" disabled={actionLoading} className="primary-button danger-button">
              Transfer
            </button>
          </form>

          <div className="danger-zone-delete">
            <div>
              <strong>Delete project workspace</strong>
              <p className="muted">Permanently delete this project and revoke collaborator access.</p>
            </div>
            <button
              type="button"
              onClick={handleDeleteProject}
              disabled={actionLoading}
              className="primary-button danger-button"
            >
              Delete project
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
