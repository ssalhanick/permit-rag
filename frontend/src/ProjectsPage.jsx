import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import {
  fetchProjects,
  createProject,
  deleteProject,
  transferProjectOwnership,
  fetchProjectMembers,
  addProjectMember,
  removeProjectMember,
  fetchProjectDocuments,
} from "./api.js";

export default function ProjectsPage() {
  const { user } = useAuth();
  const [projects, setProjects] = useState([]);
  const [selectedProj, setSelectedProj] = useState(null);
  const [members, setMembers] = useState([]);
  const [docs, setDocs] = useState([]);
  
  // Form states
  const [newProjForm, setNewProjForm] = useState({ name: "", description: "", municipality: "" });
  const [newMemberForm, setNewMemberForm] = useState({ userId: "", role: "viewer" });
  const [transferOwnerId, setTransferOwnerId] = useState("");
  
  // Loading & error states
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadProjects = async () => {
    if (!user) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetchProjects();
      setProjects(res.data || []);
      if (res.data && res.data.length > 0) {
        // Keep selection or pick first
        const currentSelected = selectedProj 
          ? res.data.find(p => p.id === selectedProj.id) 
          : res.data[0];
        if (currentSelected) {
          selectProject(currentSelected);
        } else {
          selectProject(res.data[0]);
        }
      } else {
        setSelectedProj(null);
        setMembers([]);
        setDocs([]);
      }
    } catch (err) {
      setError(err.message || "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  };

  const selectProject = async (proj) => {
    setSelectedProj(proj);
    setError("");
    setSuccess("");
    setTransferOwnerId("");
    setNewMemberForm({ userId: "", role: "viewer" });
    try {
      const [membersRes, docsRes] = await Promise.all([
        fetchProjectMembers(proj.id),
        fetchProjectDocuments(proj.id)
      ]);
      setMembers(membersRes.data || []);
      setDocs(docsRes.data || []);
    } catch (err) {
      setError(`Failed to fetch project details: ${err.message}`);
    }
  };

  useEffect(() => {
    loadProjects();
  }, [user]);

  if (!user) {
    return (
      <main className="page">
        <section className="panel">
          <h2>Projects & Collaboration</h2>
          <p className="muted">Please sign in to manage and collaborate on projects.</p>
          <Link to="/auth" className="button nav-link nav-link-active" style={{ display: "inline-block", textAlign: "center" }}>
            Go to Sign In
          </Link>
        </section>
      </main>
    );
  }

  // Find user's role in the active project
  const myMemberRecord = members.find(m => m.user_id === user.id);
  const myRole = selectedProj?.owner_user_id === user.id ? "owner" : (myMemberRecord?.role || "viewer");
  const isOwner = myRole === "owner";
  const canManage = isOwner;

  const handleCreateProject = async (e) => {
    e.preventDefault();
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      const res = await createProject({
        name: newProjForm.name,
        description: newProjForm.description || null,
        municipality: newProjForm.municipality || null
      });
      setNewProjForm({ name: "", description: "", municipality: "" });
      setSuccess(`Project "${res.data.name}" created successfully!`);
      // Reload and select new
      const currentList = await fetchProjects();
      setProjects(currentList.data || []);
      const createdProj = currentList.data.find(p => p.id === res.data.id);
      if (createdProj) {
        selectProject(createdProj);
      }
    } catch (err) {
      setError(err.message || "Failed to create project.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!selectedProj) return;
    if (!window.confirm(`Are you sure you want to delete project "${selectedProj.name}"? This cannot be undone.`)) {
      return;
    }
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await deleteProject(selectedProj.id);
      setSuccess(`Project deleted.`);
      setSelectedProj(null);
      await loadProjects();
    } catch (err) {
      setError(err.message || "Failed to delete project.");
      setActionLoading(false);
    }
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!selectedProj) return;
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await addProjectMember(selectedProj.id, newMemberForm.userId, newMemberForm.role);
      setSuccess("Member added to project!");
      setNewMemberForm({ userId: "", role: "viewer" });
      const membersRes = await fetchProjectMembers(selectedProj.id);
      setMembers(membersRes.data || []);
    } catch (err) {
      setError(err.message || "Failed to add member.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveMember = async (userId, username) => {
    if (!selectedProj) return;
    if (!window.confirm(`Remove collaborator "${username}" from project?`)) {
      return;
    }
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await removeProjectMember(selectedProj.id, userId);
      setSuccess("Collaborator removed.");
      const membersRes = await fetchProjectMembers(selectedProj.id);
      setMembers(membersRes.data || []);
    } catch (err) {
      setError(err.message || "Failed to remove member.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleTransferOwnership = async (e) => {
    e.preventDefault();
    if (!selectedProj) return;
    if (!window.confirm("Are you sure you want to transfer ownership? You will lose owner controls!")) {
      return;
    }
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await transferProjectOwnership(selectedProj.id, transferOwnerId);
      setSuccess("Project ownership transferred successfully!");
      setTransferOwnerId("");
      await loadProjects();
    } catch (err) {
      setError(err.message || "Failed to transfer ownership.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <main className="page project-page">
      <div className="project-grid">
        {/* Sidebar: Projects List */}
        <section className="panel project-list-panel">
          <h3>My Projects</h3>
          {loading && <p>Loading projects...</p>}
          {!loading && projects.length === 0 && <p className="muted">No projects found.</p>}
          <ul className="project-list-items">
            {projects.map((p) => {
              const active = selectedProj && selectedProj.id === p.id;
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    className={`project-list-item-btn ${active ? "active" : ""}`}
                    onClick={() => selectProject(p)}
                  >
                    <strong>{p.name}</strong>
                    {p.municipality && <span className="muni-badge">{p.municipality}</span>}
                  </button>
                </li>
              );
            })}
          </ul>

          <hr style={{ margin: "20px 0", borderColor: "#f1f5f9" }} />

          {/* Create Project Form */}
          <h4>New Project</h4>
          <form onSubmit={handleCreateProject} className="form mini-form">
            <div>
              <label htmlFor="projName">Project Name</label>
              <input
                id="projName"
                value={newProjForm.name}
                onChange={(e) => setNewProjForm({ ...newProjForm, name: e.target.value })}
                placeholder="e.g. Backyard Pool"
                required
              />
            </div>
            <div>
              <label htmlFor="projDesc">Description</label>
              <textarea
                id="projDesc"
                rows={2}
                value={newProjForm.description}
                onChange={(e) => setNewProjForm({ ...newProjForm, description: e.target.value })}
                placeholder="Brief summary..."
              />
            </div>
            <div>
              <label htmlFor="projMuni">Default Municipality</label>
              <input
                id="projMuni"
                value={newProjForm.municipality}
                onChange={(e) => setNewProjForm({ ...newProjForm, municipality: e.target.value })}
                placeholder="e.g. dallas"
              />
            </div>
            <button type="submit" disabled={actionLoading} className="secondary-button" style={{ width: "100%" }}>
              Create Project
            </button>
          </form>
        </section>

        {/* Main Panel: Selected Project Detail */}
        <section className="panel project-detail-panel">
          {selectedProj ? (
            <>
              <div className="project-detail-header">
                <h2>{selectedProj.name}</h2>
                <span className="role-badge">Role: {myRole.toUpperCase()}</span>
              </div>
              <p className="project-description">{selectedProj.description || "No description provided."}</p>

              <div className="project-meta-grid">
                <div>
                  <strong>Default Jurisdiction: </strong>
                  <span>{selectedProj.municipality || "None (Global search)"}</span>
                </div>
                <div>
                  <strong>Project ID: </strong>
                  <code style={{ fontSize: "0.8rem", background: "#f1f5f9", padding: "2px 4px", borderRadius: "4px" }}>
                    {selectedProj.id}
                  </code>
                </div>
              </div>

              {error && <div className="error-box" style={{ marginTop: "14px" }}>{error}</div>}
              {success && <div className="success-box" style={{ marginTop: "14px" }}>{success}</div>}

              {/* Collaborators Section */}
              <div className="project-section">
                <h3>Collaborators ({members.length + 1})</h3>
                <table className="doc-table">
                  <thead>
                    <tr>
                      <th>Collaborator</th>
                      <th>Email</th>
                      <th>Role</th>
                      {canManage && <th>Action</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {/* Owner row */}
                    <tr>
                      <td>
                        <strong>Creator (Owner)</strong>
                      </td>
                      <td>-</td>
                      <td><span className="badge badge-owner">Owner</span></td>
                      {canManage && <td>-</td>}
                    </tr>
                    {/* Other members */}
                    {members.map((m) => (
                      <tr key={m.user_id}>
                        <td>{m.username} {m.user_id === user.id && "(You)"}</td>
                        <td>{m.email}</td>
                        <td>
                          <span className={`badge badge-${m.role}`}>
                            {m.role}
                          </span>
                        </td>
                        {canManage && (
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

                {/* Add Member Form (Owner only) */}
                {canManage && (
                  <form onSubmit={handleAddMember} className="form inline-form" style={{ marginTop: "12px", display: "flex", gap: "8px", alignItems: "flex-end" }}>
                    <div style={{ flex: 1 }}>
                      <label htmlFor="newMemberId">Add Member (User UUID)</label>
                      <input
                        id="newMemberId"
                        value={newMemberForm.userId}
                        onChange={(e) => setNewMemberForm({ ...newMemberForm, userId: e.target.value })}
                        placeholder="Paste user UUID here"
                        required
                      />
                    </div>
                    <div style={{ width: "120px" }}>
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
                    <button type="submit" disabled={actionLoading} className="secondary-button" style={{ height: "36px" }}>
                      Add
                    </button>
                  </form>
                )}
              </div>

              {/* Shared Documents Section */}
              <div className="project-section" style={{ marginTop: "24px" }}>
                <h3>Shared Documents ({docs.length})</h3>
                <p className="muted">These regulatory documents are bound to this project workspace.</p>
                {docs.length === 0 ? (
                  <p className="muted" style={{ fontStyle: "italic" }}>No documents shared yet. Go to the "Documents" browser tab to share.</p>
                ) : (
                  <table className="doc-table">
                    <thead>
                      <tr>
                        <th>Doc ID</th>
                        <th>Municipality</th>
                        <th>Status</th>
                        <th>Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {docs.map((d) => (
                        <tr key={d.id}>
                          <td>
                            <strong>{d.doc_id}</strong>
                          </td>
                          <td>{d.municipality}</td>
                          <td>{d.document_status}</td>
                          <td>{d.doc_type}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Advanced Operations (Owner only) */}
              {isOwner && (
                <div className="project-section danger-zone" style={{ marginTop: "32px", borderTop: "1px solid #fee2e2", paddingTop: "20px" }}>
                  <h4 style={{ color: "#991b1b", margin: "0 0 10px" }}>Danger Zone</h4>
                  
                  {/* Transfer Ownership */}
                  <form onSubmit={handleTransferOwnership} className="form inline-form" style={{ display: "flex", gap: "8px", alignItems: "flex-end", marginBottom: "14px" }}>
                    <div style={{ flex: 1 }}>
                      <label htmlFor="transferId" style={{ color: "#991b1b" }}>Transfer Ownership (New Owner UUID)</label>
                      <input
                        id="transferId"
                        value={transferOwnerId}
                        onChange={(e) => setTransferOwnerId(e.target.value)}
                        placeholder="Paste new owner's user UUID"
                        required
                      />
                    </div>
                    <button type="submit" disabled={actionLoading} className="primary-button" style={{ background: "#dc2626" }}>
                      Transfer
                    </button>
                  </form>

                  {/* Delete Project */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <strong style={{ color: "#991b1b" }}>Delete Project Workspace</strong>
                      <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.85rem" }}>
                        Permanently delete project and revoke collaborator access. This cannot be undone.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleDeleteProject}
                      disabled={actionLoading}
                      className="primary-button"
                      style={{ background: "#dc2626" }}
                    >
                      Delete Project
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div style={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center", minHeight: "300px" }}>
              <p className="muted" style={{ fontSize: "1.1rem" }}>Select a project or create a new one to get started.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
