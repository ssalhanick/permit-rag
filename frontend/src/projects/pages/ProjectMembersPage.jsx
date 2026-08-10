import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  addProjectMember,
  deleteProject,
  fetchProjectMembers,
  hardDeleteProject,
  removeProjectMember,
  setProjectStatus,
  transferProjectOwnership,
} from "../../api.js";
import { useAuth } from "../../context/AuthContext.jsx";
import Avatar from "../../components/Avatar.jsx";
import { useProject } from "../ProjectContext.jsx";
import { Users, UserPlus, ShieldAlert, AlertTriangle, CheckCircle, Trash2, Shield, UserX, ArrowRightLeft, Archive } from "lucide-react";

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
      setSuccess("Member added successfully.");
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
      setSuccess("Ownership transferred successfully.");
      setTransferOwnerId("");
    } catch (err) {
      setError(err.message || "Failed to transfer ownership.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleArchived = async () => {
    setActionLoading(true);
    setError("");
    try {
      await setProjectStatus(projectId, !project?.is_archived);
      setSuccess(project?.is_archived ? "Project marked ongoing." : "Project archived.");
    } catch (err) {
      setError(err.message || "Failed to update project status.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleSoftDeleteProject = async () => {
    if (!window.confirm(`Move "${project?.name}" to trash? Room scans are kept, and you can restore it later.`)) {
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

  const handleHardDeleteProject = async () => {
    if (
      !window.confirm(
        `Permanently delete "${project?.name}"? This also deletes any documents uploaded only to this project. This cannot be undone.`
      )
    ) {
      return;
    }
    setActionLoading(true);
    setError("");
    try {
      await hardDeleteProject(projectId);
      navigate("/projects");
    } catch (err) {
      setError(err.message || "Failed to permanently delete project.");
      setActionLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
      {/* ── Breadcrumbs ── */}
      <nav className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 flex items-center gap-1.5">
        <Link to="/projects" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          Projects
        </Link>
        <span>/</span>
        <Link to={`/projects/${projectId}`} className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          {project?.name || "Dashboard"}
        </Link>
        <span>/</span>
        <span className="text-slate-900 dark:text-slate-100 font-bold">Members & Access</span>
      </nav>

      {/* ── Page Header ── */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
              Project Members & Permissions
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
              Manage collaborators, access privileges, and workspace administration.
            </p>
          </div>
        </div>

        <span className="text-xs font-semibold px-3 py-1 rounded-full bg-blue-100 dark:bg-blue-900/60 text-blue-800 dark:text-blue-200 border border-blue-200 dark:border-blue-800">
          Your Role: <strong className="capitalize">{role}</strong>
        </span>
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="p-4 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* ── Collaborators Card Panel ── */}
      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-4">Project Collaborators</h3>

        {loading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400 py-4">Loading collaborators…</p>
        ) : (
          <div className="overflow-x-auto mb-6">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                  <th className="pb-3 px-2">Collaborator</th>
                  <th className="pb-3 px-2">Email</th>
                  <th className="pb-3 px-2">Role</th>
                  {isOwner && <th className="pb-3 px-2 text-right">Action</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/80 font-medium text-slate-800 dark:text-slate-200">
                {members.map((m) => (
                  <tr key={m.user_id} className="hover:bg-slate-50/60 dark:hover:bg-slate-700/40 transition-colors">
                    <td className="py-3.5 px-2 font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                      <Avatar user={m} className="member-avatar" />
                      {m.role === "owner" && <Shield className="w-4 h-4 text-blue-600 dark:text-blue-400" />}
                      {m.username} {m.user_id === user?.id && <span className="text-blue-600 dark:text-blue-400 font-bold">(You)</span>}
                    </td>
                    <td className="py-3.5 px-2 text-slate-500 dark:text-slate-400">{m.email}</td>
                    <td className="py-3.5 px-2">
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold capitalize ${
                        m.role === "owner"
                          ? "bg-blue-100 dark:bg-blue-900/60 text-blue-800 dark:text-blue-200"
                          : m.role === "editor"
                          ? "bg-purple-100 dark:bg-purple-900/60 text-purple-800 dark:text-purple-200"
                          : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"
                      }`}>
                        {m.role}
                      </span>
                    </td>
                    {isOwner && (
                      <td className="py-3.5 px-2 text-right">
                        {m.role === "owner" ? (
                          <span className="text-slate-400">—</span>
                        ) : (
                          <button
                            type="button"
                            className="text-xs font-semibold text-rose-600 dark:text-rose-400 hover:underline flex items-center gap-1 ml-auto"
                            onClick={() => handleRemoveMember(m.user_id, m.username)}
                            disabled={actionLoading}
                          >
                            <UserX className="w-3.5 h-3.5" /> Remove
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Inline Add Member Form */}
        {isOwner && (
          <form onSubmit={handleAddMember} className="p-4 bg-slate-50 dark:bg-slate-900/60 rounded-xl border border-slate-200 dark:border-slate-700 space-y-3">
            <div className="flex items-center gap-2">
              <UserPlus className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">Add Collaborator</h4>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                type="text"
                value={newMemberForm.userId}
                onChange={(e) => setNewMemberForm({ ...newMemberForm, userId: e.target.value })}
                placeholder="User UUID"
                required
                className="sm:col-span-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <select
                value={newMemberForm.role}
                onChange={(e) => setNewMemberForm({ ...newMemberForm, role: e.target.value })}
                className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="viewer">Viewer (Read-only)</option>
                <option value="editor">Editor (Can edit)</option>
              </select>
            </div>
            <div className="flex justify-end pt-1">
              <button type="submit" disabled={actionLoading} className="tt-btn-primary text-xs px-4 py-2 rounded-xl">
                Add Collaborator
              </button>
            </div>
          </form>
        )}
      </div>

      {/* ── Danger Zone Card Panel ── */}
      {isOwner && (
        <div className="bg-rose-50/40 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/60 rounded-2xl p-6 sm:p-8 shadow-sm space-y-6">
          <div className="flex items-center gap-2 border-b border-rose-200/80 dark:border-rose-900/50 pb-4">
            <ShieldAlert className="w-5 h-5 text-rose-600 dark:text-rose-400" />
            <h3 className="text-base font-extrabold text-rose-900 dark:text-rose-300">Danger Zone (Owner Controls)</h3>
          </div>

          {/* Transfer Ownership */}
          <form onSubmit={handleTransferOwnership} className="space-y-2">
            <label className="block text-xs font-bold uppercase tracking-wider text-rose-900 dark:text-rose-200">
              Transfer Project Ownership
            </label>
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                value={transferOwnerId}
                onChange={(e) => setTransferOwnerId(e.target.value)}
                placeholder="New owner user UUID"
                required
                className="flex-1 bg-white dark:bg-slate-900 border border-rose-300 dark:border-rose-900/80 rounded-xl px-3.5 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-rose-500"
              />
              <button
                type="submit"
                disabled={actionLoading}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold flex items-center gap-1.5 justify-center transition-colors disabled:opacity-50"
              >
                <ArrowRightLeft className="w-3.5 h-3.5" /> Transfer Ownership
              </button>
            </div>
          </form>

          {/* Archive / Ongoing Status */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-4 border-t border-rose-200/60 dark:border-rose-900/40">
            <div>
              <strong className="text-sm text-slate-900 dark:text-slate-100 block">Project Status</strong>
              <p className="text-xs text-slate-600 dark:text-slate-300 mt-0.5">
                Archiving sets an archived tag on the projects list without revoking access.
              </p>
            </div>
            <button
              type="button"
              onClick={handleToggleArchived}
              disabled={actionLoading}
              className="tt-btn-secondary text-xs px-4 py-2 rounded-xl flex items-center gap-1.5 self-start sm:self-auto"
            >
              <Archive className="w-3.5 h-3.5 text-slate-500" />
              {project?.is_archived ? "Mark Ongoing" : "Archive Project"}
            </button>
          </div>

          {/* Soft Delete */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-4 border-t border-rose-200/60 dark:border-rose-900/40">
            <div>
              <strong className="text-sm text-slate-900 dark:text-slate-100 block">Move Workspace to Trash</strong>
              <p className="text-xs text-slate-600 dark:text-slate-300 mt-0.5">
                Moves project to trash and revokes collaborator access. Scans are preserved.
              </p>
            </div>
            <button
              type="button"
              onClick={handleSoftDeleteProject}
              disabled={actionLoading}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-xs font-bold flex items-center gap-1.5 self-start sm:self-auto transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" /> Delete Project
            </button>
          </div>

          {/* Hard Delete */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-4 border-t border-rose-200/60 dark:border-rose-900/40">
            <div>
              <strong className="text-sm text-rose-900 dark:text-rose-200 block">Permanently Delete Workspace</strong>
              <p className="text-xs text-rose-800/80 dark:text-rose-300/80 mt-0.5">
                Irreversible. Permanently purges project data and exclusive documents.
              </p>
            </div>
            <button
              type="button"
              onClick={handleHardDeleteProject}
              disabled={actionLoading}
              className="px-4 py-2 bg-rose-700 hover:bg-rose-800 text-white rounded-xl text-xs font-extrabold flex items-center gap-1.5 self-start sm:self-auto transition-colors disabled:opacity-50"
            >
              <ShieldAlert className="w-3.5 h-3.5" /> Permanently Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
