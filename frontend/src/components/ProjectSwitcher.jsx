import React, { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { useIsSuperAdmin } from "../hooks/useIsSuperAdmin.js";
import { fetchProjects } from "../api.js";
import { Check, ChevronDown, Folder, Lock, Search } from "lucide-react";

export default function ProjectSwitcher({ onSelect }) {
  const { user, activeProject, setActiveProject } = useAuth();
  const isSuperAdmin = useIsSuperAdmin();
  const userId = user?.id || user?.user_id;
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [justSelected, setJustSelected] = useState(false);
  const [error, setError] = useState("");
  const containerRef = useRef(null);

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

  const displayList = projects;

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
    // Other users' projects render inert for superadmins (see the list item
    // below) -- this is a defense-in-depth guard against that ever being
    // bypassed, not the only thing preventing the switch.
    if (isSuperAdmin && projectObj.owner_user_id && projectObj.owner_user_id !== userId) {
      return;
    }
    // setActiveProject expects a plain project id string, not the whole
    // project object -- passing the object sent a nested value where the
    // backend PATCH expects a UUID, so the switch silently never took effect.
    try {
      await setActiveProject(projectObj.id);
    } catch (err) {
      setError(err.message || "Failed to switch project.");
      return;
    }
    setError("");
    setJustSelected(true);
    setOpen(false);
    setSearch("");
    setTimeout(() => setJustSelected(false), 2500);

    if (onSelect) {
      onSelect();
    }
  };

  const selectedName = activeProject?.name || "No project selected";

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
        <div className="absolute left-0 right-0 sm:right-auto top-full z-50 mt-1.5 w-full sm:min-w-[260px] max-w-[calc(100vw-2.5rem)] rounded-xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-1">
          <div className="p-2 border-b border-slate-800">
            <div className="relative w-full">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                autoFocus
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search projects..."
                className="w-full pl-8 pr-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {error && (
            <p className="px-3 py-1.5 text-[11px] font-semibold text-red-400 bg-red-950/40 border-b border-slate-800">
              {error}
            </p>
          )}

          <ul role="listbox" className="max-h-56 overflow-y-auto divide-y divide-slate-800/50 p-1">
            {loading && <li className="px-3 py-2 text-xs text-slate-400">Loading projects…</li>}
            {!loading && filtered.length === 0 && projects.length === 0 && (
              <li className="px-3 py-3 text-xs text-slate-400">
                <p className="mb-2">You don't have any projects yet.</p>
                <NavLink
                  to="/kickoff"
                  onClick={() => setOpen(false)}
                  className="inline-flex items-center gap-1 font-semibold text-blue-400 hover:text-blue-300"
                >
                  Create your first project →
                </NavLink>
              </li>
            )}
            {!loading && filtered.length === 0 && projects.length > 0 && (
              <li className="px-3 py-2 text-xs text-slate-400">No matching projects found.</li>
            )}
            {!loading &&
              filtered.map((p) => {
                const isSelected = activeProject?.id === p.id || activeProject?.name === p.name;
                const isOtherUsersProject = isSuperAdmin && p.owner_user_id && p.owner_user_id !== userId;
                return (
                  <li key={p.id || p.name} role="option" aria-selected={isSelected} aria-disabled={isOtherUsersProject || undefined}>
                    <button
                      type="button"
                      disabled={isOtherUsersProject}
                      className={`flex w-full items-center justify-between px-3 py-2 rounded-lg text-left text-xs transition-colors ${
                        isOtherUsersProject
                          ? "text-slate-500 cursor-default opacity-60"
                          : isSelected
                          ? "bg-blue-900/40 text-blue-200 font-semibold"
                          : "text-slate-200 hover:bg-slate-800/80"
                      }`}
                      onClick={() => handlePick(p)}
                    >
                      <div className="flex flex-col min-w-0">
                        <span className="truncate flex items-center gap-1.5">
                          {p.name}
                          {isOtherUsersProject && <Lock className="w-3 h-3 flex-shrink-0" />}
                        </span>
                        {isOtherUsersProject ? (
                          <span className="text-[10px] text-slate-500">
                            Owned by {p.owner_username || p.owner_email || "another user"}
                          </span>
                        ) : (
                          p.category && <span className="text-[10px] text-slate-400">{p.category}</span>
                        )}
                      </div>
                      {isSelected && !isOtherUsersProject && (
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
