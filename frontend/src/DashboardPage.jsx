import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import { fetchProjects } from "./api.js";
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
  Check
} from "lucide-react";

export default function DashboardPage() {
  const { user, setActiveProject } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState([]);
  const [showAddTaskForm, setShowAddTaskForm] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskProject, setNewTaskProject] = useState("");
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

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    fetchProjects({})
      .then((res) => {
        const loadedProjects = res.data || [];
        setProjects(loadedProjects);
        if (loadedProjects.length > 0 && !newTaskProject) {
          setNewTaskProject(loadedProjects[0].name);
        }
      })
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, [user]);

  const activeProjects = projects.filter((p) => !p.is_archived);

  // Utility helper to safely convert strings or numbers into numeric values
  const parseMoneyNum = (val) => {
    if (typeof val === "number") return isNaN(val) ? 0 : val;
    if (!val) return 0;
    const num = parseFloat(String(val).replace(/[^0-9.]/g, ""));
    return isNaN(num) ? 0 : num;
  };

  // Dynamic budget calculations based on real project data
  const totalBudget = projects.reduce((acc, p) => acc + parseMoneyNum(p.budget), 0);
  const totalSpent = projects.reduce((acc, p) => acc + parseMoneyNum(p.spent), 0);

  const toggleTask = (id) => {
    setTasks(
      tasks.map((t) => (t.id === id ? { ...t, completed: !t.completed } : t))
    );
  };

  const handleAddTask = (e) => {
    e.preventDefault();
    if (!newTaskTitle.trim()) return;
    const newTask = {
      id: Date.now(),
      title: newTaskTitle.trim(),
      project: newTaskProject || (projects[0]?.name || "General"),
      dueDate: newTaskDueDate || "Soon",
      priority: newTaskPriority,
      completed: false,
    };
    setTasks([newTask, ...tasks]);
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
              ${totalSpent > 0 ? totalSpent.toLocaleString() : "0"} spent
            </div>
          </div>
        </div>

        {/* Card 4: Project Status */}
        <div className="tt-stat-card">
          <div className="tt-stat-icon-wrapper tt-icon-green">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div className="tt-stat-content">
            <div className="tt-stat-value">
              {totalSpent <= totalBudget ? "On Track" : "Over Budget"}
            </div>
            <div className="tt-stat-label">
              {activeProjects.length > 0 ? "Projects active" : "No active projects"}
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
            {activeProjects.map((p) => (
              <div
                key={p.id}
                className="tt-project-card tt-project-card-clickable"
                onClick={(e) => handleOpenProject(e, p.id)}
              >
                <div className="tt-project-card-header">
                  <div>
                    <h3 className="tt-project-title">{p.name}</h3>
                    <span className="tt-project-badge tt-badge-in-progress">
                      In Progress
                    </span>
                  </div>
                </div>

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
                    <strong>{p.municipality || "Local"}</strong>
                  </div>
                  <div className="tt-project-duedate text-blue-600 font-medium flex items-center">
                    <span>Open Dashboard</span>
                    <ArrowRight className="w-3.5 h-3.5 ml-1" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Upcoming Tasks Section ── */}
      <section className="tt-section">
        <div className="tt-section-header">
          <div className="flex items-center gap-2">
            <h2 className="tt-section-title">Upcoming Tasks</h2>
            <button
              type="button"
              className="tt-btn-add-task-inline"
              onClick={() => setShowAddTaskForm(!showAddTaskForm)}
            >
              <Plus className="w-4 h-4 mr-1" /> Add Task
            </button>
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
                value={newTaskProject}
                onChange={(e) => setNewTaskProject(e.target.value)}
                className="tt-select"
              >
                {projects.length > 0 ? (
                  projects.map((p) => (
                    <option key={p.id} value={p.name}>
                      {p.name}
                    </option>
                  ))
                ) : (
                  <option value="General Project">General Project</option>
                )}
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
            <div className="p-6 text-center text-slate-500">
              <CheckSquare className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm">No tasks added yet. Click "+ Add Task" to create your first task.</p>
            </div>
          ) : (
            <ul className="tt-tasks-list">
              {tasks.map((t) => (
                <li
                  key={t.id}
                  className={`tt-task-item ${t.completed ? "tt-task-completed" : ""}`}
                >
                  <label className="tt-checkbox-container">
                    <input
                      type="checkbox"
                      checked={t.completed}
                      onChange={() => toggleTask(t.id)}
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
                    <span className="tt-project-tag">{t.project}</span>
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
