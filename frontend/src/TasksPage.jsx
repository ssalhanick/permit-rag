import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Check, Search, Calendar, ChevronDown, ChevronUp } from "lucide-react";

export default function TasksPage() {
  const [tasks, setTasks] = useState([
    {
      id: 1,
      title: "Get three quotes for cabinet install",
      project: "Kitchen Renovation",
      dueDate: "2d overdue",
      urgency: "urgent", // red dot
      priority: "High",
      completed: false,
    },
    {
      id: 2,
      title: "Order countertop samples",
      project: "Kitchen Renovation",
      dueDate: "1d",
      urgency: "soon", // orange dot
      priority: "Medium",
      completed: false,
    },
    {
      id: 3,
      title: "Confirm electrician start date",
      project: "Electrical Panel Upgrade",
      dueDate: "3d",
      urgency: "soon",
      priority: "High",
      completed: false,
    },
    {
      id: 4,
      title: "Drywall Patching & Sanding",
      project: "Kitchen Renovation",
      dueDate: "5d",
      urgency: "urgent",
      priority: "Medium",
      completed: false,
    },
    {
      id: 5,
      title: "Inspect Circuit Breaker Labeling",
      project: "Electrical Panel Upgrade",
      dueDate: "9d",
      urgency: "urgent",
      priority: "Low",
      completed: false,
    },
    {
      id: 6,
      title: "Schedule Plumbing Rough-in Inspection",
      project: "Kitchen Renovation",
      dueDate: "19d",
      urgency: "later", // blue dot
      priority: "High",
      completed: false,
    },
    {
      id: 7,
      title: "Select paint color for trim",
      project: "Basement Finishing",
      dueDate: "24d",
      urgency: "soon",
      priority: "Low",
      completed: false,
    },
    {
      id: 8,
      title: "Finalize landscaping layout plan",
      project: "Deck & Landscaping",
      dueDate: "45d",
      urgency: "urgent",
      priority: "Medium",
      completed: false,
    },
    {
      id: 9,
      title: "Review permit requirements",
      project: "Kitchen Renovation",
      dueDate: "Done",
      urgency: "completed",
      priority: "High",
      completed: true,
    },
    {
      id: 10,
      title: "Order tile samples for backsplash",
      project: "Kitchen Renovation",
      dueDate: "Done",
      urgency: "completed",
      priority: "Medium",
      completed: true,
    },
    {
      id: 11,
      title: "Disconnect old appliance lines",
      project: "Kitchen Renovation",
      dueDate: "Done",
      urgency: "completed",
      priority: "High",
      completed: true,
    },
    {
      id: 12,
      title: "Submit electrical permit application",
      project: "Electrical Panel Upgrade",
      dueDate: "Done",
      urgency: "completed",
      priority: "High",
      completed: true,
    },
    {
      id: 13,
      title: "Clear out basement storage area",
      project: "Basement Finishing",
      dueDate: "Done",
      urgency: "completed",
      priority: "Low",
      completed: true,
    },
  ]);

  const [showCompleted, setShowCompleted] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);

  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskProject, setNewTaskProject] = useState("Kitchen Renovation");
  const [newTaskPriority, setNewTaskPriority] = useState("Medium");
  const [newTaskDueDate, setNewTaskDueDate] = useState("7d");

  const openTasks = tasks.filter((t) => !t.completed);
  const completedTasks = tasks.filter((t) => t.completed);

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
      project: newTaskProject,
      dueDate: newTaskDueDate || "Soon",
      urgency: "soon",
      priority: newTaskPriority,
      completed: false,
    };
    setTasks([newTask, ...tasks]);
    setNewTaskTitle("");
    setShowAddForm(false);
  };

  const filteredOpenTasks = openTasks.filter((t) => {
    const q = searchQuery.trim().toLowerCase();
    return (
      !q ||
      t.title.toLowerCase().includes(q) ||
      t.project.toLowerCase().includes(q)
    );
  });

  const renderUrgencyDot = (urgency, dueDate) => {
    let dotColor = "bg-sky-500";
    if (urgency === "urgent" || dueDate.includes("overdue")) {
      dotColor = "bg-rose-500";
    } else if (urgency === "soon") {
      dotColor = "bg-amber-500";
    }
    return <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${dotColor}`} />;
  };

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
        <button
          type="button"
          className="tt-btn-primary tt-new-project-btn"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          <Plus className="w-5 h-5 mr-1.5 stroke-[2.5]" />
          Add task
        </button>
      </header>

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
              value={newTaskProject}
              onChange={(e) => setNewTaskProject(e.target.value)}
              className="tt-select"
            >
              <option value="Kitchen Renovation">Kitchen Renovation</option>
              <option value="Electrical Panel Upgrade">Electrical Panel Upgrade</option>
              <option value="Basement Finishing">Basement Finishing</option>
              <option value="Deck & Landscaping">Deck & Landscaping</option>
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
              key={t.id}
              className="p-4 hover:bg-slate-50/80 transition-colors flex items-center justify-between gap-4"
            >
              {/* Left Column: Circular Checkbox */}
              <div className="flex items-center gap-3.5 flex-1 min-w-0">
                <button
                  type="button"
                  onClick={() => toggleTask(t.id)}
                  className="w-5 h-5 rounded-full border-2 border-slate-300 hover:border-blue-600 flex items-center justify-center flex-shrink-0 transition-colors"
                  aria-label={`Mark "${t.title}" as complete`}
                />

                {/* Middle Column: Title + Subtitle Project */}
                <div className="flex flex-col min-w-0">
                  <span className="text-sm font-semibold text-slate-900 truncate">
                    {t.title}
                  </span>
                  <span className="text-xs text-slate-500 mt-0.5 truncate">
                    {t.project}
                  </span>
                </div>
              </div>

              {/* Right Column: Color-coded Dot + Due Date */}
              <div className="flex items-center text-xs text-slate-500 font-medium flex-shrink-0">
                {renderUrgencyDot(t.urgency, t.dueDate)}
                <span className={t.dueDate.includes("overdue") ? "text-rose-600 font-semibold" : ""}>
                  • {t.dueDate}
                </span>
              </div>
            </li>
          ))}

          {filteredOpenTasks.length === 0 && (
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
                  key={t.id}
                  className="p-4 flex items-center justify-between gap-4 opacity-60 bg-slate-50/40"
                >
                  <div className="flex items-center gap-3.5 flex-1 min-w-0">
                    <button
                      type="button"
                      onClick={() => toggleTask(t.id)}
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
                        {t.project}
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
