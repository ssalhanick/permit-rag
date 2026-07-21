import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ProjectKickoffSummary from "../../components/ProjectKickoffSummary.jsx";
import ScanLibraryList from "../../components/ScanLibraryList.jsx";
import MaterialsEstimatePanel from "../../components/MaterialsEstimatePanel.jsx";
import ProjectMapImage from "../../components/ProjectMapImage.jsx";
import { fetchProjectDocuments, fetchProjectRoomScans, fetchQueryHistory } from "../../api.js";
import { formatKickoffSummary } from "../../projectKickoffSummary.js";
import { buildKickoffPath } from "../../projectKickoffRoutes.js";
import { useProject } from "../ProjectContext.jsx";

/**
 * Project overview — kickoff summary, linked scans, recent queries.
 */
export default function ProjectDashboardPage() {
  const { project, canEdit, projectId } = useProject();
  const [scans, setScans] = useState([]);
  const [queries, setQueries] = useState([]);
  const [documents, setDocuments] = useState([]);

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

  const kickoff = formatKickoffSummary(project);
  const roomRows = scans.filter((s) => s.scan_type === "room");
  const activeRoom = roomRows.find((r) => r.is_active);

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
    </div>
  );
}
