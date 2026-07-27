import React, { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { fetchProjects } from "../api.js";
import { Check, ChevronDown, Folder, Search } from "lucide-react";

export default function ProjectSwitcher({ onSelect }) {
  const { activeProject, setActiveProject } = useAuth();
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [justSelected, setJustSelected] = useState(false);
  const containerRef = useRef(null);

  // Default starter projects if backend project list is empty
  const starterProjects = [
    { id: "proj-kitchen-renovation", name: "Kitchen Renovation", category: "Kitchen" },
    { id: "proj-basement-finishing", name: "Basement Finishing", category: "Basement" },
    { id: "proj-electrical-panel-upgrade", name: "Electrical Panel Upgrade", category: "Electrical" },
    { id: "proj-master-bath-retile", name: "Master Bath Retile", category: "Bathroom" },
    { id: "proj-deck-landscaping", name: "Deck & Landscaping", category: "Exterior" },
  ];

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    fetchProjects({ status: "ongoing" })
      .then((res) => {
        if (!cancelled) setProjects(res.data || []);
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
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

  const displayList = projects.length > 0 ? projects : starterProjects;

  const filtered = displayList.filter((p) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      p.name?.toLowerCase().includes(q) ||
      p.address?.toLowerCase().includes(q) ||
      p.municipality?.toLowerCase().includes(q) ||
      p.category?.toLowerCase().includes(q)
    );
  });

  const handlePick = async (projectObj) => {
    try {
      await setActiveProject(projectObj);
    } catch {
      // Fallback local set
      setActiveProject(projectObj);
    }
    setJustSelected(true);
    setOpen(false);
    setSearch("");
    setTimeout(() => setJustSelected(false), 2500);

    if (onSelect) {
      onSelect();
    }
  };

  const selectedName = activeProject?.name || "Kitchen Renovation";

  return (
    <div ref={containerRef} className="relative w-full">
      {/* Selected Project Label & Trigger Button */}
      <div className="mb-1 text-[11px] font-bold uppercase tracking-wider text-slate-400">
        Selected Project
      </div>

      <button
        type="button"
        className={`w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg border text-left transition-all ${
          justSelected
            ? "bg-emerald-950/60 border-emerald-500 text-emerald-300 ring-2 ring-emerald-500/30"
            : "bg-slate-800/90 hover:bg-slate-800 border-slate-700 text-slate-100"
        }`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Folder className="w-4 h-4 text-blue-400 flex-shrink-0" />
          <span className="text-xs font-semibold truncate">
            {selectedName}
          </span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {justSelected && (
            <span className="text-[10px] font-bold text-emerald-400 bg-emerald-900/80 px-1.5 py-0.5 rounded">
              Selected!
            </span>
          )}
          <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      {/* Dropdown Options Box */}
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-full min-w-[260px] rounded-xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-1">
          <div className="p-2 border-b border-slate-800">
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700">
              <Search className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
              <input
                type="text"
                autoFocus
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search projects..."
                className="w-full bg-transparent text-xs text-slate-100 placeholder-slate-400 focus:outline-none"
              />
            </div>
          </div>

          <ul role="listbox" className="max-h-56 overflow-y-auto divide-y divide-slate-800/50 p-1">
            {loading && <li className="px-3 py-2 text-xs text-slate-400">Loading projects…</li>}
            {!loading && filtered.length === 0 && (
              <li className="px-3 py-2 text-xs text-slate-400">No matching projects found.</li>
            )}
            {!loading &&
              filtered.map((p) => {
                const isSelected = activeProject?.id === p.id || activeProject?.name === p.name;
                return (
                  <li key={p.id || p.name} role="option" aria-selected={isSelected}>
                    <button
                      type="button"
                      className={`flex w-full items-center justify-between px-3 py-2 rounded-lg text-left text-xs transition-colors ${
                        isSelected
                          ? "bg-blue-900/40 text-blue-200 font-semibold"
                          : "text-slate-200 hover:bg-slate-800/80"
                      }`}
                      onClick={() => handlePick(p)}
                    >
                      <div className="flex flex-col min-w-0">
                        <span className="truncate">{p.name}</span>
                        {p.category && <span className="text-[10px] text-slate-400">{p.category}</span>}
                      </div>
                      {isSelected && (
                        <Check className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 ml-2 stroke-[3]" />
                      )}
                    </button>
                  </li>
                );
              })}
          </ul>

          <div className="border-t border-slate-800 p-2 bg-slate-950/40">
            <NavLink
              to="/projects"
              className="block px-2 py-1 text-center text-xs font-semibold text-sky-400 hover:text-sky-300 transition-colors"
              onClick={() => {
                setOpen(false);
                if (onSelect) onSelect();
              }}
            >
              Browse all projects →
            </NavLink>
          </div>
        </div>
      )}
    </div>
  );
}
