import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import { useIsSuperAdmin } from "./hooks/useIsSuperAdmin.js";
import { fetchProjects } from "./api.js";
import { loadProjectTasks, saveProjectTasks } from "./services/taskStorage.js";
import { parseMoneyNum } from "./utils/parseMoneyNum.js";
import {
  FolderKanban,
  CalendarCheck,
  DollarSign,
  ShieldCheck,
  Plus,
  Clock,
  CheckSquare,
  ArrowRight,
  ChevronRight,
  Check,
  Lock
} from "lucide-react";

export default function DashboardPage() {
  const { user, setActiveProject } = useAuth();
  const isSuperAdmin = useIsSuperAdmin();
  const userId = user?.id || user?.user_id;
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  // Flat list of tasks aggregated across all of the user's real projects
  const [tasks, setTasks] = useState([]);
  const [showAddTaskForm, setShowAddTaskForm] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskProjectId, setNewTaskProjectId] = useState("");
  const [newTaskPriority, setNewTaskPriority] = useState("Medium");
  const [newTaskDueDate, setNewTaskDueDate] = useState("");

  // Time-of-day greeting
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 18) return "Good afternoon";
    return "Good evening";
  };

  const username = user?.username || user?.email?.split("@")[0] || "User";

  const loadAllTasks = (projectList) => {
    const aggregated = projectList.flatMap((p) =>
      loadProjectTasks(p.id).map((t) => ({ ...t, projectId: p.id, projectName: p.name }))
    );
    setTasks(aggregated);
  };

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    fetchProjects({})
      .then((res) => {
        const loadedProjects = res.data || [];
        setProjects(loadedProjects);
        if (loadedProjects.length > 0 && !newTaskProjectId) {
          setNewTaskProjectId(loadedProjects[0].id);
        }
        loadAllTasks(loadedProjects);
      })
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, [user]);

  const activeProjects = projects.filter((p) => !p.is_archived);

  // Dynamic budget calculations based on real project data
  const totalBudget = projects.reduce((acc, p) => acc + parseMoneyNum(p.budget), 0);

  const toggleTask = (projectId, taskId) => {
    const updated = loadProjectTasks(projectId).map((t) =>
      t.id === taskId ? { ...t, completed: !t.completed } : t
    );
    saveProjectTasks(projectId, updated);
    loadAllTasks(projects);
  };

  const handleAddTask = (e) => {
    e.preventDefault();
    if (!newTaskTitle.trim() || !newTaskProjectId) return;
    const newTask = {
      id: `task_${Date.now()}`,
      title: newTaskTitle.trim(),
      category: "GENERAL",
      priority: newTaskPriority,
      urgencyDot: "bg-sky-500",
      dueDate: newTaskDueDate || "Soon",
      completed: false,
      createdAt: new Date().toISOString(),
    };
    saveProjectTasks(newTaskProjectId, [newTask, ...loadProjectTasks(newTaskProjectId)]);
    loadAllTasks(projects);
    setNewTaskTitle("");
    setNewTaskDueDate("");
    setShowAddTaskForm(false);
  };

  const getPriorityStyle = (priority) => {
    switch (priority?.toLowerCase()) {
      case "high":
        return "tt-priority-high";
      case "medium":
        return "tt-priority-medium";
      case "low":
      default:
        return "tt-priority-low";
    }
  };

  const handleOpenProject = (e, projectId) => {
    e.stopPropagation();
    setActiveProject(projectId);
    navigate(`/projects/${projectId}/dashboard`);
  };

  const [activeTab, setActiveTab] = useState("overview");

  return (
    <main className="tt-dashboard-container">
      {/* ── Top Header Section ── */}
      <header className="tt-dashboard-header">
        <div>
          <h1 className="tt-greeting-title">
            {getGreeting()}, <span className="tt-username-highlight">{username}</span>.
          </h1>
          <p className="tt-greeting-subtitle">
            Here's what's happening across your home projects.
          </p>
        </div>
        <Link to="/kickoff" className="tt-btn-primary tt-new-project-btn">
          <Plus className="w-5 h-5 mr-1.5 stroke-[2.5]" />
          New Project
        </Link>
      </header>

      {/* ── Secondary Dashboard Navigation Bar ── */}
      <nav className="border-b border-slate-200 dark:border-slate-700 mb-6 flex flex-wrap items-center gap-4 sm:gap-6 text-sm font-semibold">
        <button
          type="button"
          onClick={() => setActiveTab("overview")}
          className={`pb-2.5 transition-colors border-b-2 ${
            activeTab === "overview"
              ? "border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400"
              : "border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
          }`}
        >
          Overview & Profile
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("projects")}
          className={`pb-2.5 transition-colors border-b-2 ${
            activeTab === "projects"
              ? "border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400"
              : "border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
          }`}
        >
          My Projects ({projects.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("tasks")}
          className={`pb-2.5 transition-colors border-b-2 ${
            activeTab === "tasks"
              ? "border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400"
              : "border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
          }`}
        >
          Tasks ({tasks.filter((t) => !t.completed).length})
        </button>
        <Link
          to="/query"
          className="pb-2.5 transition-colors border-b-2 border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
        >
          AI Query Assistant
        </Link>
      </nav>

      {/* ── Summary Stats Grid (4 Cards) ── */}
      <section className="tt-stats-grid" aria-label="Summary Statistics">
        {/* Card 1: Active Projects */}
        <div className="tt-stat-card">
          <div className="tt-stat-icon-wrapper tt-icon-teal">
            <FolderKanban className="w-6 h-6" />
          </div>
          <div className="tt-stat-content">
            <div className="tt-stat-value">
              {activeProjects.length} Active {activeProjects.length === 1 ? "Project" : "Projects"}
            </div>
            <div className="tt-stat-label">{projects.length} total in account</div>
          </div>
        </div>

        {/* Card 2: Tasks Due Soon */}
        <div className="tt-stat-card">
          <div className="tt-stat-icon-wrapper tt-icon-orange">
            <CalendarCheck className="w-6 h-6" />
          </div>
          <div className="tt-stat-content">
            <div className="tt-stat-value">
              {tasks.filter((t) => !t.completed).length} Tasks Due Soon
            </div>
            <div className="tt-stat-label">
              {tasks.length} total tasks
            </div>
          </div>
        </div>

        {/* Card 3: Total Budget */}
        <div className="tt-stat-card">
          <div className="tt-stat-icon-wrapper tt-icon-purple">
            <DollarSign className="w-6 h-6" />
          </div>
          <div className="tt-stat-content">
            <div className="tt-stat-value">
              ${totalBudget > 0 ? totalBudget.toLocaleString() : "0"} Total Budget
            </div>
            <div className="tt-stat-label">
              Across {projects.length} {projects.length === 1 ? "project" : "projects"}
            </div>
          </div>
        </div>

        {/* Card 4: Archived Projects */}
        <div className="tt-stat-card">
          <div className="tt-stat-icon-wrapper tt-icon-green">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div className="tt-stat-content">
            <div className="tt-stat-value">
              {projects.length - activeProjects.length} Archived
            </div>
            <div className="tt-stat-label">
              {activeProjects.length} still active
            </div>
          </div>
        </div>
      </section>

      {/* ── Active Projects Section ── */}
      <section className="tt-section">
        <div className="tt-section-header">
          <h2 className="tt-section-title">Active Projects</h2>
          <Link to="/projects" className="tt-link-see-all">
            View All <ChevronRight className="w-4 h-4 ml-0.5" />
          </Link>
        </div>

        {loading ? (
          <p className="text-slate-500 py-4">Loading active projects…</p>
        ) : activeProjects.length === 0 ? (
          <div className="tt-tasks-card p-8 text-center">
            <FolderKanban className="w-10 h-10 text-slate-300 mx-auto mb-2" />
            <h3 className="text-base font-semibold text-slate-700">No Active Projects Yet</h3>
            <p className="text-sm text-slate-500 mb-4">
              Get started by creating your first home improvement project.
            </p>
            <Link to="/kickoff" className="tt-btn-primary">
              <Plus className="w-4 h-4 mr-1" /> Create Project
            </Link>
          </div>
        ) : (
          <div className="tt-projects-grid">
            {activeProjects.map((p) => {
              // Superadmins see every project blended into this list (backend
              // read-bypass, docs/cognito_groups_rbac.md); other users' rows
              // are shown but fully inert -- visible for context, not a
              // read-only detail view -- so an admin can't casually open
              // someone else's workspace from a dashboard grid.
              const isOtherUsersProject = isSuperAdmin && p.owner_user_id && p.owner_user_id !== userId;
              return (
              <div
                key={p.id}
                className={`tt-project-card${isOtherUsersProject ? " tt-project-card-inert" : " tt-project-card-clickable"}`}
                onClick={isOtherUsersProject ? undefined : (e) => handleOpenProject(e, p.id)}
                aria-disabled={isOtherUsersProject || undefined}
              >
                <div className="tt-project-card-header">
                  <div>
                    <h3 className="tt-project-title">
                      {p.name}
                      {isOtherUsersProject && <Lock className="tt-project-lock-icon" aria-hidden="true" />}
                    </h3>
                    <span className="tt-project-badge tt-badge-in-progress">
                      In Progress
                    </span>
                  </div>
                </div>

                {isOtherUsersProject && (
                  <p className="tt-project-owner-label">
                    Owned by {p.owner_username || p.owner_email || "another user"}
                  </p>
                )}

                <p className="text-sm text-slate-500 line-clamp-1 mt-1">
                  {p.address || p.description || "Home improvement project workspace"}
                </p>

                <div className="tt-progress-section my-3">
                  <div className="tt-progress-labels">
                    <span className="tt-progress-title">Progress</span>
                    <span className="tt-progress-percent">{p.progress || 0}%</span>
                  </div>
                  <div className="tt-progress-bar-bg">
                    <div
                      className="tt-progress-bar-fill"
                      style={{ width: `${p.progress || 0}%` }}
                    ></div>
                  </div>
                </div>

                <div className="tt-project-footer">
                  <div className="tt-project-budget">
                    <span className="tt-budget-label">Municipality:</span>{" "}
                    <strong className="uppercase tracking-wider font-semibold text-[11px]">{p.municipality || "Local"}</strong>
                  </div>
                  {isOtherUsersProject ? (
                    <div className="tt-project-duedate text-slate-400 font-medium flex items-center">
                      <Lock className="w-3 h-3 mr-1" />
                      <span>Not yours to open</span>
                    </div>
                  ) : (
                    <div className="tt-project-duedate text-blue-600 font-medium flex items-center">
                      <span>Open Dashboard</span>
                      <ArrowRight className="w-3.5 h-3.5 ml-1" />
                    </div>
                  )}
                </div>
              </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ── Upcoming Tasks Section ── */}
      <section className="tt-section">
        <div className="tt-section-header">
          <div className="flex items-center gap-2">
            <h2 className="tt-section-title">Upcoming Tasks</h2>
            {projects.length > 0 && (
              <button
                type="button"
                className="tt-btn-primary inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                onClick={() => setShowAddTaskForm(!showAddTaskForm)}
              >
                <Plus className="w-4 h-4" /> Add Task
              </button>
            )}
          </div>
          <Link to="/tasks" className="tt-link-see-all">
            View All <ChevronRight className="w-4 h-4 ml-0.5" />
          </Link>
        </div>

        {/* Add Task Form Collapsible */}
        {showAddTaskForm && (
          <form onSubmit={handleAddTask} className="tt-add-task-card">
            <h4 className="text-sm font-semibold text-slate-800 mb-3">Add New Task</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              <input
                type="text"
                placeholder="Task title (e.g. Apply for Building Permit)"
                value={newTaskTitle}
                onChange={(e) => setNewTaskTitle(e.target.value)}
                required
                className="tt-input"
              />
              <select
                value={newTaskProjectId}
                onChange={(e) => setNewTaskProjectId(e.target.value)}
                className="tt-select"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <select
                value={newTaskPriority}
                onChange={(e) => setNewTaskPriority(e.target.value)}
                className="tt-select"
              >
                <option value="High">High Priority</option>
                <option value="Medium">Medium Priority</option>
                <option value="Low">Low Priority</option>
              </select>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="tt-btn-secondary"
                onClick={() => setShowAddTaskForm(false)}
              >
                Cancel
              </button>
              <button type="submit" className="tt-btn-primary">
                Save Task
              </button>
            </div>
          </form>
        )}

        <div className="tt-tasks-card">
          {tasks.length === 0 ? (
            <div className="profile-empty-state">
              <CheckSquare className="profile-empty-state-icon" aria-hidden="true" />
              {projects.length === 0 ? (
                <>
                  <p>Create a project to start adding tasks.</p>
                  <Link to="/kickoff" className="tt-btn-primary">
                    Start a project
                  </Link>
                </>
              ) : (
                <div className="py-6 text-center">
                  <p className="text-sm text-slate-500 mb-4">No tasks found for your projects.</p>
                  <button
                    type="button"
                    className="tt-btn-primary text-sm px-6 py-3 rounded-xl font-bold inline-flex items-center gap-2 shadow-md hover:shadow-lg transition-all"
                    onClick={() => setShowAddTaskForm(true)}
                  >
                    <Plus className="w-5 h-5 stroke-[2.5]" /> Add Task
                  </button>
                </div>
              )}
            </div>
          ) : (
            <ul className="tt-tasks-list">
              {tasks.map((t) => (
                <li
                  key={`${t.projectId}-${t.id}`}
                  className={`tt-task-item ${t.completed ? "tt-task-completed" : ""}`}
                >
                  <label className="tt-checkbox-container">
                    <input
                      type="checkbox"
                      checked={t.completed}
                      onChange={() => toggleTask(t.projectId, t.id)}
                      className="tt-custom-checkbox-input"
                    />
                    <span className="tt-custom-checkbox">
                      {t.completed && <Check className="w-3.5 h-3.5 text-white stroke-[3]" />}
                    </span>
                  </label>

                  <div className="tt-task-info">
                    <span className="tt-task-title">{t.title}</span>
                  </div>

                  <div className="tt-task-meta">
                    <span className="tt-project-tag">{t.projectName}</span>
                    <span className="tt-task-duedate">Due {t.dueDate}</span>
                    <span
                      className={`tt-priority-badge ${getPriorityStyle(t.priority)}`}
                    >
                      {t.priority}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  );
}
