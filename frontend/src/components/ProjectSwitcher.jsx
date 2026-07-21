import React, { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { fetchProjects } from "../api.js";

export default function ProjectSwitcher() {
  const { activeProject, setActiveProject } = useAuth();
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    fetchProjects({ status: "ongoing" })
      .then((res) => {
        if (!cancelled) setProjects(res.data || []);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = projects.filter((p) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      p.name?.toLowerCase().includes(q) ||
      p.address?.toLowerCase().includes(q) ||
      p.municipality?.toLowerCase().includes(q)
    );
  });

  const handlePick = async (projectId) => {
    await setActiveProject(projectId);
    setOpen(false);
    setSearch("");
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        className="nav-link flex items-center gap-1.5"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {activeProject?.name || "Select project"}
        <span aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-72 rounded-md border border-slate-700 bg-slate-900 shadow-lg">
          <div className="p-2">
            <input
              type="text"
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search projects…"
              className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1 text-sm text-slate-100"
            />
          </div>
          <ul role="listbox" className="max-h-64 overflow-y-auto">
            {loading && <li className="px-3 py-2 text-sm text-slate-400">Loading…</li>}
            {!loading && filtered.length === 0 && (
              <li className="px-3 py-2 text-sm text-slate-400">No matching projects.</li>
            )}
            {!loading &&
              filtered.map((p) => (
                <li key={p.id} role="option" aria-selected={activeProject?.id === p.id}>
                  <button
                    type="button"
                    className="flex w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-slate-800"
                    onClick={() => handlePick(p.id)}
                  >
                    <span className="font-medium text-slate-100">{p.name}</span>
                    {p.address && <span className="text-xs text-slate-400">{p.address}</span>}
                  </button>
                </li>
              ))}
          </ul>
          <div className="border-t border-slate-700 p-2">
            <NavLink
              to="/projects"
              className="block px-1 py-1 text-sm text-sky-400 hover:text-sky-300"
              onClick={() => setOpen(false)}
            >
              Browse all projects →
            </NavLink>
          </div>
        </div>
      )}
    </div>
  );
}
