import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Check, Search, ChevronDown, ChevronUp } from "lucide-react";
import { fetchProjects } from "./api.js";
import { loadProjectTasks, saveProjectTasks } from "./services/taskStorage.js";

export default function TasksPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  // Flat list of tasks aggregated across all of the user's real projects
  const [tasks, setTasks] = useState([]);

  const [showCompleted, setShowCompleted] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);

  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskProjectId, setNewTaskProjectId] = useState("");
  const [newTaskPriority, setNewTaskPriority] = useState("Medium");
  const [newTaskDueDate, setNewTaskDueDate] = useState("");

  const loadAllTasks = (projectList) => {
    const aggregated = projectList.flatMap((p) =>
      loadProjectTasks(p.id).map((t) => ({ ...t, projectId: p.id, projectName: p.name }))
    );
    setTasks(aggregated);
  };

  useEffect(() => {
    fetchProjects({})
      .then((res) => {
        const list = res.data || [];
        setProjects(list);
        if (list.length > 0) setNewTaskProjectId(list[0].id);
        loadAllTasks(list);
      })
      .catch(() => {
        setProjects([]);
        setTasks([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const openTasks = tasks.filter((t) => !t.completed);
  const completedTasks = tasks.filter((t) => t.completed);

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
    setShowAddForm(false);
  };

  const filteredOpenTasks = openTasks.filter((t) => {
    const q = searchQuery.trim().toLowerCase();
    return (
      !q ||
      t.title.toLowerCase().includes(q) ||
      t.projectName?.toLowerCase().includes(q)
    );
  });

  return (
    <main className="tt-dashboard-container">
      {/* ── Top Header Section ── */}
      <header className="tt-dashboard-header">
        <div>
          <h1 className="tt-greeting-title">Tasks</h1>
          <p className="tt-greeting-subtitle">
            <strong>{openTasks.length} open</strong> · {completedTasks.length} completed
          </p>
        </div>
        {projects.length > 0 && (
          <button
            type="button"
            className="tt-btn-primary tt-new-project-btn"
            onClick={() => setShowAddForm(!showAddForm)}
          >
            <Plus className="w-5 h-5 mr-1.5 stroke-[2.5]" />
            Add task
          </button>
        )}
      </header>

      {!loading && projects.length === 0 && (
        <div className="tt-add-task-card mb-6 text-center py-8">
          <p className="text-sm text-slate-600 mb-3">
            You don't have any projects yet — create one to start adding tasks.
          </p>
          <Link to="/kickoff" className="tt-btn-primary inline-flex items-center gap-1.5">
            <Plus className="w-4 h-4" /> Create your first project
          </Link>
        </div>
      )}

      {/* Collapsible Add Task Form */}
      {showAddForm && (
        <form onSubmit={handleAddTask} className="tt-add-task-card mb-6">
          <h4 className="text-sm font-semibold text-slate-800 mb-3">Add New Task</h4>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
            <input
              type="text"
              placeholder="Task title (e.g. Order drywall sheets)"
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
                <option key={p.id} value={p.id}>{p.name}</option>
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
            <input
              type="text"
              placeholder="Due (e.g. 5d or Aug 12)"
              value={newTaskDueDate}
              onChange={(e) => setNewTaskDueDate(e.target.value)}
              className="tt-input"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="tt-btn-secondary"
              onClick={() => setShowAddForm(false)}
            >
              Cancel
            </button>
            <button type="submit" className="tt-btn-primary">
              Save Task
            </button>
          </div>
        </form>
      )}

      {/* ── Main Tasks Content Card ── */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-8">
        {/* Card Top Toolbar Header */}
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">All Tasks</h3>

          <div className="flex items-center gap-4">
            <div className="tt-search-box max-w-xs py-1">
              <Search className="w-3.5 h-3.5 text-slate-400 mr-1.5" />
              <input
                type="text"
                placeholder="Search tasks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="tt-search-input text-xs"
              />
            </div>

            <button
              type="button"
              onClick={() => setShowCompleted(!showCompleted)}
              className="text-xs font-semibold text-slate-500 hover:text-blue-600 transition-colors flex items-center gap-1"
            >
              {showCompleted ? "Hide completed" : `Show completed (${completedTasks.length})`}
              {showCompleted ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Open Tasks List */}
        <ul className="divide-y divide-slate-100">
          {filteredOpenTasks.map((t) => (
            <li
              key={`${t.projectId}-${t.id}`}
              className="p-4 hover:bg-slate-50/80 transition-colors flex items-center justify-between gap-4"
            >
              {/* Left Column: Circular Checkbox */}
              <div className="flex items-center gap-3.5 flex-1 min-w-0">
                <button
                  type="button"
                  onClick={() => toggleTask(t.projectId, t.id)}
                  className="w-5 h-5 rounded-full border-2 border-slate-300 hover:border-blue-600 flex items-center justify-center flex-shrink-0 transition-colors"
                  aria-label={`Mark "${t.title}" as complete`}
                />

                {/* Middle Column: Title + Subtitle Project */}
                <div className="flex flex-col min-w-0">
                  <span className="text-sm font-semibold text-slate-900 truncate">
                    {t.title}
                  </span>
                  <span className="text-xs text-slate-500 mt-0.5 truncate">
                    {t.projectName}
                  </span>
                </div>
              </div>

              {/* Right Column: Color-coded Dot + Due Date */}
              <div className="flex items-center text-xs text-slate-500 font-medium flex-shrink-0">
                <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${t.urgencyDot || "bg-sky-500"}`} />
                <span className={t.dueDate?.includes("overdue") ? "text-rose-600 font-semibold" : ""}>
                  • {t.dueDate}
                </span>
              </div>
            </li>
          ))}

          {!loading && filteredOpenTasks.length === 0 && projects.length > 0 && (
            <li className="p-8 text-center text-slate-500 text-sm">
              No open tasks found.
            </li>
          )}
        </ul>

        {/* Completed Tasks Accordion */}
        {showCompleted && completedTasks.length > 0 && (
          <div className="border-t-2 border-slate-100 bg-slate-50/50">
            <div className="px-4 py-2 bg-slate-100/60 text-xs font-bold uppercase tracking-wider text-slate-500">
              Completed ({completedTasks.length})
            </div>
            <ul className="divide-y divide-slate-100">
              {completedTasks.map((t) => (
                <li
                  key={`${t.projectId}-${t.id}`}
                  className="p-4 flex items-center justify-between gap-4 opacity-60 bg-slate-50/40"
                >
                  <div className="flex items-center gap-3.5 flex-1 min-w-0">
                    <button
                      type="button"
                      onClick={() => toggleTask(t.projectId, t.id)}
                      className="w-5 h-5 rounded-full bg-blue-600 border-2 border-blue-600 flex items-center justify-center flex-shrink-0"
                      aria-label={`Mark "${t.title}" as incomplete`}
                    >
                      <Check className="w-3.5 h-3.5 text-white stroke-[3]" />
                    </button>
                    <div className="flex flex-col min-w-0">
                      <span className="text-sm font-semibold text-slate-800 line-through">
                        {t.title}
                      </span>
                      <span className="text-xs text-slate-500 line-through">
                        {t.projectName}
                      </span>
                    </div>
                  </div>
                  <span className="text-xs text-slate-400">Done</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </main>
  );
}
