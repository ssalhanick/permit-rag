import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchProjectDocuments } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";
import { FileText, ExternalLink, AlertTriangle, Plus, ShieldCheck } from "lucide-react";

/**
 * Regulatory documents bound to this project workspace.
 */
export default function ProjectDocumentsPage() {
  const { project, projectId } = useProject();
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fetchProjectDocuments(projectId);
        setDocs(res.data || []);
      } catch (err) {
        setError(err.message || "Failed to load documents.");
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
      {/* ── Breadcrumb Navigation ── */}
      <nav className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 flex items-center gap-1.5">
        <Link to="/projects" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          Projects
        </Link>
        <span>/</span>
        <Link to={`/projects/${projectId}`} className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          {project?.name || "Dashboard"}
        </Link>
        <span>/</span>
        <span className="text-slate-900 dark:text-slate-100 font-bold">Regulatory Documents</span>
      </nav>

      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
              Regulatory Documents
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
              Code manuals, municipal ordinances, and building guidelines attached to this workspace.
            </p>
          </div>
        </div>

        <Link
          to="/documents"
          className="tt-btn-primary text-xs px-4 py-2.5 rounded-xl flex items-center gap-1.5 self-start sm:self-auto"
        >
          <Plus className="w-3.5 h-3.5" /> Share More Documents
        </Link>
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ── Card Panel Container ── */}
      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm">
        {loading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400 py-4">Loading regulatory documents…</p>
        ) : docs.length === 0 ? (
          <div className="text-center py-10 space-y-3">
            <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mx-auto">
              <FileText className="w-6 h-6" />
            </div>
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              No regulatory documents shared with this workspace yet.
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm mx-auto">
              Link building codes and municipal guidelines to provide context for AI responses.
            </p>
            <Link
              to="/documents"
              className="inline-flex items-center gap-1.5 text-xs font-bold text-blue-600 dark:text-blue-400 hover:underline pt-2"
            >
              Browse Global Document Vault <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                  <th className="pb-3 px-2">Document ID</th>
                  <th className="pb-3 px-2">Municipality / Scope</th>
                  <th className="pb-3 px-2">Type</th>
                  <th className="pb-3 px-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/80 font-medium text-slate-800 dark:text-slate-200">
                {docs.map((d) => (
                  <tr key={d.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-700/40 transition-colors">
                    <td className="py-3.5 px-2 font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                      {d.doc_id}
                    </td>
                    <td className="py-3.5 px-2 text-slate-600 dark:text-slate-300 capitalize">{d.municipality || "Universal"}</td>
                    <td className="py-3.5 px-2 text-slate-500 dark:text-slate-400 uppercase tracking-wide text-[10px]">
                      {d.doc_type || "Standard"}
                    </td>
                    <td className="py-3.5 px-2 text-right">
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-200">
                        <ShieldCheck className="w-3 h-3" />
                        {d.document_status || "Active"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
