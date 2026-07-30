import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Filter, MapPin } from "lucide-react";
import { fetchMarketplaceProjects } from "../../api.js";
import { SERVICE_MUNICIPALITIES, TRADES } from "../contractorOptions.js";

const selectClass =
  "bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500";

export default function ContractorDashboardPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [trade, setTrade] = useState("");
  const [municipality, setMunicipality] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    fetchMarketplaceProjects({ trade: trade || undefined, municipality: municipality || undefined })
      .then((res) => {
        if (active) {
          setProjects(res.data || []);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.message || "Failed to load open projects.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [trade, municipality]);

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">Open Projects</h1>
        <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
          Browse projects open for bidding, filtered by trade and municipality.
        </p>
      </div>

      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 sm:p-5 shadow-sm mb-6 flex flex-wrap items-center gap-3">
        <Filter className="w-4 h-4 text-slate-400" />
        <select value={trade} onChange={(e) => setTrade(e.target.value)} className={selectClass}>
          <option value="">All trades</option>
          {TRADES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select value={municipality} onChange={(e) => setMunicipality(e.target.value)} className={selectClass}>
          <option value="">All municipalities</option>
          {SERVICE_MUNICIPALITIES.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="p-4 mb-6 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading open projects…</p>
      ) : projects.length === 0 ? (
        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-8 text-center text-sm text-slate-500 dark:text-slate-400">
          No open projects match these filters right now.
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((project) => (
            <Link
              key={project.id}
              to={`/marketplace/${project.id}`}
              className="block bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 sm:p-5 shadow-sm hover:border-blue-400 dark:hover:border-blue-600 transition-colors"
            >
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <div className="font-bold text-slate-900 dark:text-slate-100 text-sm">{project.name}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5" />
                    {project.municipality || "Municipality not set"}
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 justify-end">
                  {(project.work_types || []).slice(0, 3).map((wt) => (
                    <span
                      key={wt}
                      className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold border bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300 border-slate-300 dark:border-slate-700"
                    >
                      {wt}
                    </span>
                  ))}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
