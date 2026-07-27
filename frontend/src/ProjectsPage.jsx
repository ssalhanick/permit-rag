import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import { fetchProjects } from "./api.js";
import {
  Plus,
  TrendingUp,
  Search,
  Zap,
  Droplets,
  Hammer,
  Trees,
  Home,
  Clock,
  CheckCircle2,
  Trash2,
  Layers,
  ArrowRight,
  FolderKanban
} from "lucide-react";

export default function ProjectsPage() {
  const { user, activeProject, setActiveProject } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedProjectId = searchParams.get("projectId");
  const [userProjects, setUserProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filterTab, setFilterTab] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");



  const loadProjects = async () => {
    if (!user) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetchProjects({});
      setUserProjects(res.data || []);
    } catch (err) {
      setError(err.message || "Failed to load account projects.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, [user]);

  useEffect(() => {
    if (requestedProjectId) {
      navigate(`/projects/${requestedProjectId}/dashboard`, { replace: true });
    }
  }, [requestedProjectId, navigate]);

  const handleSetActive = async (e, projectId) => {
    e.stopPropagation();
    try {
      await setActiveProject(projectId);
    } catch (err) {
      setError(err.message || "Failed to set active project.");
    }
  };

  // Convert backend user projects into matching card structures
  const formattedUserProjects = userProjects.map((p) => ({
    id: p.id,
    isRealBackend: true,
    name: p.name,
    category: p.municipality || "Home Project",
    status: p.is_archived ? "On Hold" : "In Progress",
    progress: p.progress || 45,
    tasksDone: p.tasks_done || 4,
    tasksTotal: p.tasks_total || 8,
    spent: p.spent || 4500,
    budget: p.budget || 10000,
    dueDate: "Active",
    daysRemaining: "Ongoing",
    iconType: "home",
    address: p.address,
    isArchived: p.is_archived,
  }));

  // Display strictly real user backend projects from the database
  const displayProjects = formattedUserProjects;

  // Filter projects by active status tab and search query
  const filteredProjects = displayProjects.filter((p) => {
    const matchesTab =
      filterTab === "all" ||
      (filterTab === "inprogress" && !p.isArchived && p.status !== "Complete") ||
      (filterTab === "onhold" && p.isArchived) ||
      (filterTab === "complete" && p.status === "Complete");

    const q = searchQuery.trim().toLowerCase();
    const matchesSearch =
      !q ||
      p.name?.toLowerCase().includes(q) ||
      p.category?.toLowerCase().includes(q) ||
      p.address?.toLowerCase().includes(q);

    return matchesTab && matchesSearch;
  });

  // Utility helper to safely convert strings or numbers into numeric values
  const parseMoneyNum = (val) => {
    if (typeof val === "number") return isNaN(val) ? 0 : val;
    if (!val) return 0;
    const num = parseFloat(String(val).replace(/[^0-9.]/g, ""));
    return isNaN(num) ? 0 : num;
  };

  // Calculate portfolio total budget and spend from active project list
  const totalSpent = displayProjects.reduce((sum, p) => sum + parseMoneyNum(p.spent), 0);
  const totalBudget = displayProjects.reduce((sum, p) => sum + parseMoneyNum(p.budget), 0);
  const budgetPercentage =
    totalBudget > 0 ? Math.round((totalSpent / totalBudget) * 100) : 0;

  const renderProjectIcon = (type) => {
    switch (type) {
      case "electrical":
        return <Zap className="w-5 h-5 text-amber-500" />;
      case "kitchen":
      case "bath":
        return <Droplets className="w-5 h-5 text-sky-500" />;
      case "basement":
        return <Hammer className="w-5 h-5 text-indigo-500" />;
      case "exterior":
        return <Trees className="w-5 h-5 text-emerald-500" />;
      case "entry":
      default:
        return <Home className="w-5 h-5 text-blue-500" />;
    }
  };

  const getStatusBadgeStyle = (status) => {
    switch (status?.toLowerCase()) {
      case "in progress":
        return "tt-status-badge-progress";
      case "planning":
        return "tt-status-badge-planning";
      case "on hold":
        return "tt-status-badge-hold";
      case "complete":
        return "tt-status-badge-complete";
      default:
        return "tt-status-badge-progress";
    }
  };

  return (
    <main className="tt-dashboard-container">
      {/* ── Header Section ── */}
      <header className="tt-dashboard-header">
        <div>
          <h1 className="tt-greeting-title">Projects</h1>
          <p className="tt-greeting-subtitle">
            {displayProjects.length} projects across your home
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link to="/projects/trash" className="tt-btn-secondary flex items-center gap-1.5">
            <Trash2 className="w-4 h-4 text-slate-400" />
            Recently deleted
          </Link>
          <Link to="/profile/room-scans" className="tt-btn-secondary flex items-center gap-1.5">
            <Layers className="w-4 h-4 text-slate-400" />
            Scan library
          </Link>
          <Link to="/kickoff" className="tt-btn-primary tt-new-project-btn">
            <Plus className="w-5 h-5 mr-1.5 stroke-[2.5]" />
            New project
          </Link>
        </div>
      </header>

      {error && <div className="error-box mb-4">{error}</div>}

      {/* ── Status Tabs & Search Toolbar ── */}
      <section className="tt-projects-toolbar">
        <div className="tt-status-pills-row" role="tablist" aria-label="Project Status Filter">
          {[
            { id: "all", label: "All" },
            { id: "inprogress", label: "In Progress" },
            { id: "onhold", label: "On Hold" },
            { id: "complete", label: "Complete" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={filterTab === tab.id}
              onClick={() => setFilterTab(tab.id)}
              className={`tt-status-pill ${
                filterTab === tab.id ? "tt-status-pill-active" : ""
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="tt-search-box max-w-xs">
          <Search className="w-4 h-4 text-slate-400 mr-2" />
          <input
            type="text"
            placeholder="Search projects..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="tt-search-input"
          />
        </div>
      </section>

      {/* ── Portfolio Budget Overview Container ── */}
      <section className="tt-portfolio-overview-card">
        <div className="tt-portfolio-header">
          <div className="flex items-center gap-2.5">
            <div className="tt-portfolio-icon-bg">
              <TrendingUp className="w-5 h-5 text-blue-600" />
            </div>
            <h3 className="tt-portfolio-title">Portfolio Budget Overview</h3>
          </div>
          <div className="tt-portfolio-amount-text">
            <strong>${totalSpent.toLocaleString()}</strong> of ${totalBudget.toLocaleString()} spent
          </div>
        </div>

        <div className="tt-portfolio-bar-bg">
          <div
            className="tt-portfolio-bar-fill"
            style={{ width: `${Math.min(budgetPercentage, 100)}%` }}
          ></div>
        </div>
      </section>

      {/* ── Projects Cards Grid (3 Columns Layout) ── */}
      <section className="tt-section">
        {loading ? (
          <p className="text-slate-500 py-4">Loading project cards…</p>
        ) : filteredProjects.length === 0 ? (
          <div className="tt-tasks-card p-10 text-center">
            <FolderKanban className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="text-lg font-semibold text-slate-700">No Matching Projects</h3>
            <p className="text-sm text-slate-500 mb-5">
              No projects matched the selected status tab or search text.
            </p>
            <button
              type="button"
              onClick={() => {
                setFilterTab("all");
                setSearchQuery("");
              }}
              className="tt-btn-secondary"
            >
              Reset Filters
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredProjects.map((p) => (
              <div
                key={p.id}
                className="tt-project-grid-card cursor-pointer"
                onClick={() =>
                  p.isRealBackend
                    ? navigate(`/projects/${p.id}/dashboard`)
                    : navigate("/kickoff")
                }
              >
                {/* Card Top Row */}
                <div className="tt-grid-card-top">
                  <div className="flex items-center gap-3">
                    <div className="tt-project-icon-circle">
                      {renderProjectIcon(p.iconType || p.category)}
                    </div>
                    <div>
                      <h3 className="tt-grid-card-title">{p.name}</h3>
                      <span className="tt-grid-card-subtitle">{p.category}</span>
                    </div>
                  </div>
                  <span className={`tt-status-badge ${getStatusBadgeStyle(p.status)}`}>
                    {p.status}
                  </span>
                </div>

                <p className="text-xs text-slate-500 line-clamp-1 mt-2">
                  {p.address || "Home Improvement Workspace"}
                </p>

                {/* Progress Section */}
                <div className="tt-progress-section my-4">
                  <div className="tt-progress-labels">
                    <span className="tt-progress-title">Progress</span>
                    <span className="tt-progress-percent">{p.progress}%</span>
                  </div>
                  <div className="tt-progress-bar-bg">
                    <div
                      className="tt-progress-bar-fill"
                      style={{ width: `${p.progress}%` }}
                    ></div>
                  </div>
                  <div className="tt-progress-subtext">
                    {p.tasksDone} of {p.tasksTotal} tasks done
                  </div>
                </div>

                {/* Budget & Due Date Split Row */}
                <div className="tt-grid-card-footer">
                  <div className="tt-card-footer-col">
                    <span className="tt-footer-label">Budget</span>
                    <span className="tt-footer-value">
                      ${p.spent.toLocaleString()} / ${p.budget.toLocaleString()}
                    </span>
                  </div>

                  <div className="tt-card-footer-col text-right">
                    <span className="tt-footer-label">Due</span>
                    <span className="tt-footer-value">{p.dueDate}</span>
                    <span className="tt-footer-subvalue flex items-center justify-end">
                      {p.daysRemaining === "Done" ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mr-1" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-slate-400 mr-1" />
                      )}
                      {p.daysRemaining}
                    </span>
                  </div>
                </div>

                {/* Active Project Selector */}
                <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                  {activeProject?.id === p.id ? (
                    <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-100 text-blue-700">
                      Active Project
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="text-xs font-semibold text-blue-600 hover:text-blue-800"
                      onClick={(e) => handleSetActive(e, p.id)}
                    >
                      Set Active
                    </button>
                  )}
                  <span className="text-xs font-medium text-slate-500 flex items-center">
                    Dashboard <ArrowRight className="w-3 h-3 ml-1" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
