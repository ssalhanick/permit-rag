import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDocuments, fetchDocumentStatus, fetchProjects, shareDocumentToProject } from "./api.js";
import { useAuth } from "./context/AuthContext.jsx";
import DocumentAdminPanel from "./components/DocumentAdminPanel.jsx";
import { FileText, Filter, Share2, Edit3, Layers, Search, Building, RefreshCcw, Check, AlertCircle } from "lucide-react";

const DEFAULT_FILTERS = {
  municipality: "",
  status: "",
  authority: "",
  doc_type: "",
};

export default function DocumentBrowserPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [rows, setRows] = useState([]);
  const [statusBuckets, setStatusBuckets] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [shareSuccess, setShareSuccess] = useState("");
  const [shareError, setShareError] = useState("");
  const [editingDocId, setEditingDocId] = useState(null);

  const activeFilterCount = useMemo(() => {
    return Object.values(filters).filter((value) => value.trim().length > 0).length;
  }, [filters]);

  const candidateDocIds = useMemo(() => rows.map((row) => row.doc_id), [rows]);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [docsResult, statusResult] = await Promise.all([
        fetchDocuments(filters),
        fetchDocumentStatus(filters),
      ]);
      setRows(docsResult.data || []);
      setStatusBuckets(statusResult.data?.counts || []);
    } catch (requestError) {
      setError(requestError.message || "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (user) {
      fetchProjects()
        .then((res) => setProjects(res.data || []))
        .catch(() => {});
    } else {
      setProjects([]);
    }
  }, [user]);

  function handleChange(event) {
    const { name, value } = event.target;
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
  }

  const handleShare = async (docId, projId) => {
    if (!projId) return;
    setShareError("");
    setShareSuccess("");
    try {
      await shareDocumentToProject(projId, docId);
      setShareSuccess("Document shared with project successfully!");
      setTimeout(() => setShareSuccess(""), 3000);
    } catch (err) {
      setShareError(err.message || "Failed to share document.");
      setTimeout(() => setShareError(""), 3000);
    }
  };

  return (
    <main className="p-4 sm:p-6 space-y-6 max-w-7xl mx-auto">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            Document Corpus & Building Code Index
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Search, filter, and inspect municipal building compliance documents, ordinances, and building codes.
          </p>
        </div>
      </div>

      {/* Filter Toolbar Section */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 m-0">
              Filter Corpus
            </h3>
            {activeFilterCount > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 text-[10px] font-bold">
                {activeFilterCount} Active
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {activeFilterCount > 0 && (
              <button
                type="button"
                onClick={resetFilters}
                className="text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 font-semibold flex items-center gap-1"
              >
                <RefreshCcw className="w-3 h-3" />
                Clear
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
              Municipality
            </label>
            <input
              type="text"
              name="municipality"
              value={filters.municipality}
              onChange={handleChange}
              placeholder="e.g. City of Austin"
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
              Status
            </label>
            <input
              type="text"
              name="status"
              value={filters.status}
              onChange={handleChange}
              placeholder="e.g. active"
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
              Authority Level
            </label>
            <input
              type="text"
              name="authority"
              value={filters.authority}
              onChange={handleChange}
              placeholder="e.g. City / Municipal"
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
              Doc Type
            </label>
            <input
              type="text"
              name="doc_type"
              value={filters.doc_type}
              onChange={handleChange}
              placeholder="e.g. Building Code"
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl text-xs font-semibold">
          {error}
        </div>
      )}
      {shareSuccess && (
        <div className="p-3 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 rounded-xl text-xs font-semibold">
          {shareSuccess}
        </div>
      )}
      {shareError && (
        <div className="p-3 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl text-xs font-semibold">
          {shareError}
        </div>
      )}

      {/* Status Buckets Cards */}
      {statusBuckets.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {statusBuckets.map((bucket) => (
            <div
              key={bucket.status}
              className="p-3.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl flex items-center justify-between"
            >
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                  {bucket.status}
                </span>
                <span className="text-lg font-extrabold text-slate-900 dark:text-slate-100">
                  {bucket.count}
                </span>
              </div>
              <Layers className="w-5 h-5 text-blue-500 opacity-60" />
            </div>
          ))}
        </div>
      )}

      {/* Documents Data Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 m-0">
            Document Records ({rows.length})
          </h3>
          <span className="text-xs text-slate-400 font-medium">
            {loading ? "Refreshing..." : `${rows.length} indexed items`}
          </span>
        </div>

        {loading ? (
          <div className="py-12 text-center text-xs text-slate-400 animate-pulse">
            Loading document corpus...
          </div>
        ) : rows.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-400">
            No document records matched the selected criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                  <th className="pb-3 px-2">Document ID</th>
                  <th className="pb-3 px-2">Municipality</th>
                  <th className="pb-3 px-2">Type</th>
                  <th className="pb-3 px-2">Authority</th>
                  <th className="pb-3 px-2">Status</th>
                  <th className="pb-3 px-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-medium text-slate-800 dark:text-slate-200">
                {rows.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-2 font-bold text-blue-600 dark:text-blue-400">
                      {row.doc_id}
                    </td>
                    <td className="py-3 px-2 text-slate-700 dark:text-slate-300">
                      {row.municipality || "—"}
                    </td>
                    <td className="py-3 px-2 text-slate-500 dark:text-slate-400">
                      {row.doc_type || "Standard"}
                    </td>
                    <td className="py-3 px-2 text-slate-500 dark:text-slate-400">
                      {row.authority_level || "Municipal"}
                    </td>
                    <td className="py-3 px-2">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                        {row.document_status || "Active"}
                      </span>
                    </td>
                    <td className="py-3 px-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {user && (
                          <button
                            type="button"
                            onClick={() => setEditingDocId(row.doc_id)}
                            className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold flex items-center gap-1 transition-colors"
                          >
                            <Edit3 className="w-3 h-3" />
                            Edit
                          </button>
                        )}
                        {user && projects.length > 0 && (
                          <select
                            value=""
                            onChange={(e) => handleShare(row.id, e.target.value)}
                            className="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-[11px] font-semibold border-none focus:ring-1 focus:ring-blue-500"
                          >
                            <option value="">Share...</option>
                            {projects.map((p) => (
                              <option key={p.id} value={p.id}>{p.name}</option>
                            ))}
                          </select>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editingDocId && (
        <DocumentAdminPanel
          docId={editingDocId}
          candidateDocIds={candidateDocIds}
          onClose={() => setEditingDocId(null)}
          onSaved={loadDocuments}
        />
      )}
    </main>
  );
}
