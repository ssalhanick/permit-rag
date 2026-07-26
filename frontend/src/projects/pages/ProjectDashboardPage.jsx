import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import ProjectKickoffSummary from "../../components/ProjectKickoffSummary.jsx";
import ScanLibraryList from "../../components/ScanLibraryList.jsx";
import MaterialsEstimatePanel from "../../components/MaterialsEstimatePanel.jsx";
import ProjectMapImage from "../../components/ProjectMapImage.jsx";
import {
  deleteProject,
  fetchPermitStrategy,
  fetchProjectDocuments,
  fetchProjectRoomScans,
  fetchQueryHistory,
  hardDeleteProject,
} from "../../api.js";
import { formatKickoffSummary } from "../../projectKickoffSummary.js";
import { buildKickoffPath } from "../../projectKickoffRoutes.js";
import { useAuth } from "../../context/AuthContext.jsx";
import { useProject } from "../ProjectContext.jsx";

/**
 * Project overview — kickoff summary, linked scans, recent queries.
 */
export default function ProjectDashboardPage() {
  const { project, canEdit, projectId } = useProject();
  const { user } = useAuth();
  const navigate = useNavigate();
  const isSuperadmin = user?.role === "superadmin";
  const [scans, setScans] = useState([]);
  const [queries, setQueries] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [permitStrategy, setPermitStrategy] = useState(null);
  const [dangerActionLoading, setDangerActionLoading] = useState(false);
  const [dangerError, setDangerError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [scanRes, queryRes, docRes] = await Promise.all([
          fetchProjectRoomScans(projectId),
          fetchQueryHistory(projectId),
          fetchProjectDocuments(projectId),
        ]);
        setScans(scanRes.data || []);
        setQueries((queryRes.data || []).slice(0, 5));
        setDocuments(docRes.data || []);
      } catch {
        setScans([]);
        setQueries([]);
        setDocuments([]);
      }
    })();
  }, [projectId]);

  useEffect(() => {
    fetchPermitStrategy(projectId)
      .then((res) => setPermitStrategy(res.data || null))
      .catch(() => setPermitStrategy(null));
  }, [projectId]);

  const kickoff = formatKickoffSummary(project);
  const roomRows = scans.filter((s) => s.scan_type === "room");
  const activeRoom = roomRows.find((r) => r.is_active);

  const handleSuperadminSoftDelete = async () => {
    if (
      !window.confirm(
        `Move "${project?.name}" to trash? You're not a member of this project — acting as superadmin. Room scans are kept, and the project owner can restore it later.`
      )
    ) {
      return;
    }
    setDangerActionLoading(true);
    setDangerError("");
    try {
      await deleteProject(projectId);
      navigate("/projects");
    } catch (err) {
      setDangerError(err.message || "Failed to delete project.");
      setDangerActionLoading(false);
    }
  };

  const handleSuperadminHardDelete = async () => {
    const typed = window.prompt(
      `Permanently delete "${project?.name}"? This is irreversible and also deletes any documents uploaded exclusively to this project. Type DELETE to confirm.`
    );
    if ((typed || "").trim().toLowerCase() !== "delete") {
      return;
    }
    setDangerActionLoading(true);
    setDangerError("");
    try {
      await hardDeleteProject(projectId);
      navigate("/projects");
    } catch (err) {
      setDangerError(err.message || "Failed to permanently delete project.");
      setDangerActionLoading(false);
    }
  };

  return (
    <div className="project-dashboard-home">
      <section className="panel">
        <div className="project-kickoff-header">
          <h2>{project.name}</h2>
          {canEdit && (
            <Link
              to={buildKickoffPath({ mode: "wizard", projectId, returnTo: `/projects/${projectId}/dashboard` })}
              className="secondary-button"
            >
              {kickoff.hasKickoffData ? "Update setup" : "Complete setup"}
            </Link>
          )}
        </div>
        <p className="muted">{project.description || "No description yet."}</p>
        <ProjectKickoffSummary project={project} />
        {project.address && (
          <div className="mt-3">
            <ProjectMapImage
              latitude={project.latitude}
              longitude={project.longitude}
              address={project.address}
            />
          </div>
        )}
      </section>

      <section className="panel">
        <div className="dashboard-section-header">
          <h3>Documents scanned</h3>
          <Link to={`/projects/${projectId}/documents`} className="text-button">
            Manage documents →
          </Link>
        </div>
        {documents.length === 0 ? (
          <p className="muted">No documents shared to this project yet.</p>
        ) : (
          <ul className="dashboard-query-preview">
            {documents.map((d) => (
              <li key={d.id}>
                <strong>{d.doc_id}</strong>
                <span className="muted">{d.municipality} · {d.doc_type}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel dashboard-scan-promo">
        <div className="dashboard-section-header">
          <h3>Room scans on this project</h3>
          <Link to={`/projects/${projectId}/scans`} className="text-button">
            Manage scans →
          </Link>
        </div>
        {activeRoom && (
          <p className="muted">
            Active room for chat: <strong>{activeRoom.room_label}</strong>
          </p>
        )}
        <ScanLibraryList
          scans={scans}
          emptyMessage="No scans linked yet. Add from your library or scan on the Scans tab."
        />
      </section>

      {permitStrategy && permitStrategy.permits.length > 0 && (
        <section className="panel">
          <div className="dashboard-section-header">
            <h3>Permit strategy</h3>
          </div>
          <p className="muted">
            Pull order: {permitStrategy.sequence.join(" → ")}
          </p>
          <ul className="dashboard-query-preview">
            {permitStrategy.permits.map((p) => (
              <li key={p}>
                <strong>{p}</strong>
                <span className="muted">
                  {permitStrategy.fee_breakdown[p] != null
                    ? `~$${permitStrategy.fee_breakdown[p]}`
                    : "—"}
                </span>
              </li>
            ))}
          </ul>
          <p className="muted">
            Estimated permit fees: <strong>~${permitStrategy.estimated_fees_usd}</strong>
          </p>
          <p className="muted" style={{ fontSize: "0.8rem" }}>{permitStrategy.fee_disclaimer}</p>
        </section>
      )}

      <section className="panel">
        <div className="dashboard-section-header">
          <h3>Materials estimate</h3>
        </div>
        <MaterialsEstimatePanel projectId={projectId} />
      </section>

      <section className="panel">
        <div className="dashboard-section-header">
          <h3>Recent queries</h3>
          <Link to={`/projects/${projectId}/queries`} className="text-button">
            View all →
          </Link>
        </div>
        {queries.length === 0 ? (
          <p className="muted">No queries logged for this project yet.</p>
        ) : (
          <ul className="dashboard-query-preview">
            {queries.map((q) => (
              <li key={q.id}>
                <strong>{q.query_text}</strong>
                <span className="muted">{new Date(q.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {isSuperadmin && (
        <section className="panel danger-zone">
          <h3>Superadmin controls</h3>
          <p className="muted">
            You can manage this project regardless of membership. Delete actions here are
            audit-logged.
          </p>
          {dangerError && <div className="error-box">{dangerError}</div>}

          <div className="danger-zone-delete">
            <div>
              <strong>Delete project workspace</strong>
              <p className="muted">
                Moves the project to trash. The owner can restore it from their own Recently
                Deleted view.
              </p>
            </div>
            <button
              type="button"
              onClick={handleSuperadminSoftDelete}
              disabled={dangerActionLoading}
              className="primary-button danger-button"
            >
              Delete project
            </button>
          </div>

          <div className="danger-zone-delete">
            <div>
              <strong>Permanently delete</strong>
              <p className="muted">
                Irreversible. Also deletes any documents uploaded exclusively to this project.
              </p>
            </div>
            <button
              type="button"
              onClick={handleSuperadminHardDelete}
              disabled={dangerActionLoading}
              className="primary-button danger-button"
            >
              Permanently delete
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
