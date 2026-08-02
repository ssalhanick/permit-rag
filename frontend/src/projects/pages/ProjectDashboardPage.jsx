import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useProject } from "../ProjectContext.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import {
  fetchProjectRoomScans,
  fetchQueryHistory,
  fetchProjectDocuments,
  fetchPermitStrategy,
  fetchProjectCoverage,
} from "../../api.js";
import { loadProjectTasks, saveProjectTasks } from "../../services/taskStorage.js";
import { parseMoneyNum } from "../../utils/parseMoneyNum.js";
import {
  Plus,
  Check,
  ChevronDown,
  ChevronUp,
  Settings as SettingsIcon,
  FileText,
  Sparkles,
  Upload,
  Layers,
  Download,
  Eye,
  CheckCircle2,
  FileCheck,
  Package,
  ShoppingCart,
  Box,
  ArrowRight,
  AlertTriangle
} from "lucide-react";

export default function ProjectDashboardPage() {
  const { project, projectId } = useProject();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState("tasks");
  const [showNewDropdown, setShowNewDropdown] = useState(false);
  const [scans, setScans] = useState([]);
  const [queries, setQueries] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [permitStrategy, setPermitStrategy] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [selectedDocPreview, setSelectedDocPreview] = useState(null);

  // Flat task list for this project, persisted to localStorage (see taskStorage.js)
  // so it stays in sync with the global Tasks page and the Dashboard widget.
  const [tasks, setTasks] = useState([]);
  const openTasks = tasks.filter((t) => !t.completed);
  const completedTasks = tasks.filter((t) => t.completed);

  // Open tasks grouped by category for the Tasks tab display
  const projectTasks = openTasks.reduce((groups, task) => {
    const existing = groups.find((g) => g.category === task.category);
    if (existing) {
      existing.tasks.push(task);
    } else {
      groups.push({ category: task.category || "GENERAL", tasks: [task] });
    }
    return groups;
  }, []);

  const persistTasks = (next) => {
    setTasks(next);
    saveProjectTasks(projectId, next);
  };

  // Materials & Supplies List for this project
  const [materials, setMaterials] = useState([]);

  const [showAddMaterial, setShowAddMaterial] = useState(false);
  const [newMatName, setNewMatName] = useState("");
  const [newMatCat, setNewMatCat] = useState("Building Supplies");
  const [newMatQty, setNewMatQty] = useState(1);
  const [newMatPrice, setNewMatPrice] = useState(25);
  const [newMatSupplier, setNewMatSupplier] = useState("Home Depot");
  const [newMatStatus, setNewMatStatus] = useState("Needed");

  // AI LLM Generated Documents for this project
  const [generatedDocs, setGeneratedDocs] = useState([]);

  const [showCompleted, setShowCompleted] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskCategory, setNewTaskCategory] = useState("PROCUREMENT");
  const [showAddInline, setShowAddInline] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [scanRes, queryRes, docRes] = await Promise.all([
          fetchProjectRoomScans(projectId),
          fetchQueryHistory(projectId),
          fetchProjectDocuments(projectId),
        ]);
        setScans(scanRes.data || []);
        setQueries(queryRes.data || []);
        setDocuments(docRes.data || []);
      } catch {
        setScans([]);
        setQueries([]);
        setDocuments([]);
      }
    })();
  }, [projectId]);

  useEffect(() => {
    fetchPermitStrategy(projectId)
      .then((res) => setPermitStrategy(res.data || null))
      .catch(() => setPermitStrategy(null));
  }, [projectId]);

  useEffect(() => {
    fetchProjectCoverage(projectId)
      .then((res) => setCoverage(res.data || null))
      .catch(() => setCoverage(null));
  }, [projectId]);

  useEffect(() => {
    setTasks(loadProjectTasks(projectId));
  }, [projectId]);

  // Compute tasks metrics dynamically
  const openTasksCount = openTasks.length;
  const totalTasksCount = tasks.length;
  const progressPercent = totalTasksCount > 0 ? Math.round((completedTasks.length / totalTasksCount) * 100) : 0;

  // Compute live budget metrics (budget is the only real financial field — no expense
  // tracking exists yet, so there is no honest "spent" figure to show alongside it)
  const budgetTotal = parseMoneyNum(project.budget);

  // Compute materials metrics
  const totalMaterialCost = materials.reduce((acc, m) => acc + m.unitPrice * m.quantity, 0);
  const purchasedMaterialCost = materials
    .filter((m) => m.status === "Purchased" || m.status === "Delivered")
    .reduce((acc, m) => acc + m.unitPrice * m.quantity, 0);

  const toggleOpenTask = (taskId) => {
    persistTasks(tasks.map((t) => (t.id === taskId ? { ...t, completed: true } : t)));
  };

  const toggleCompletedTask = (taskId) => {
    persistTasks(
      tasks.map((t) =>
        t.id === taskId ? { ...t, completed: false, urgencyDot: "bg-sky-500", dueDate: "Soon" } : t
      )
    );
  };

  const handleAddInlineTask = (e) => {
    e.preventDefault();
    if (!newTaskTitle.trim()) return;
    const newTask = {
      id: `task_${Date.now()}`,
      title: newTaskTitle.trim(),
      category: newTaskCategory,
      priority: "Medium",
      urgencyDot: "bg-sky-500",
      dueDate: "Soon",
      completed: false,
      createdAt: new Date().toISOString(),
    };
    persistTasks([newTask, ...tasks]);
    setNewTaskTitle("");
    setShowAddInline(false);
  };

  const handleAddMaterial = (e) => {
    e.preventDefault();
    if (!newMatName.trim()) return;
    const newMat = {
      id: `mat-${Date.now()}`,
      name: newMatName.trim(),
      category: newMatCat,
      quantity: Number(newMatQty) || 1,
      unitPrice: Number(newMatPrice) || 0,
      supplier: newMatSupplier || "Home Depot",
      status: newMatStatus,
    };
    setMaterials([...materials, newMat]);
    setNewMatName("");
    setShowAddMaterial(false);
  };

  // Convert AI Document Steps into Tasks
  const handleConvertStepsToTasks = (doc) => {
    if (!doc.steps || doc.steps.length === 0) {
      alert("No individual steps found to convert.");
      return;
    }
    const newTasks = doc.steps.map((stepText, idx) => ({
      id: `task_${Date.now()}_${idx}`,
      title: stepText,
      category: "AI GENERATED",
      priority: "High",
      urgencyDot: "bg-blue-500",
      dueDate: "AI Generated",
      completed: false,
      createdAt: new Date().toISOString(),
    }));

    persistTasks([...tasks, ...newTasks]);
    setActiveTab("tasks");
    alert(`Successfully added ${newTasks.length} AI generated tasks to your project task list!`);
  };

  // Combining uploaded files & room scans for the Uploaded Documents tab
  const uploadedFiles = [
    ...documents.map((d) => ({ id: d.id, name: d.doc_id || d.filename || "Building Code Doc", type: d.doc_type || "PDF Document", date: "Uploaded" })),
    ...scans.map((s) => ({ id: s.id, name: `${s.room_label || "Room"} 3D Mesh Scan`, type: "3D Scan File", date: "Scanned" })),
  ];

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6">
      {/* ── Breadcrumbs ── */}
      <nav className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2 flex items-center gap-1.5">
        <Link to="/projects" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          Projects
        </Link>
        <span>/</span>
        <span className="text-slate-900 dark:text-slate-100">{project.name}</span>
      </nav>

      {/* ── Top Header Section (Mobile 2-Column Layout) ── */}
      <header className="mb-6 space-y-3">
        {/* Row 1: 2 Columns - Left: "Project Dashboard", Right: "+ New" Dropdown */}
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
            Project Dashboard
          </h1>

          <div className="flex items-center gap-2 relative">
            <Link
              to={`/projects/${projectId}/settings`}
              className="tt-btn-secondary flex items-center gap-1.5 text-xs px-3 py-2"
            >
              <SettingsIcon className="w-4 h-4 text-slate-400" />
              Edit
            </Link>

            {/* "+ New" Action Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowNewDropdown(!showNewDropdown)}
                className="tt-btn-primary flex items-center gap-1.5 text-xs px-3 py-2"
              >
                <Plus className="w-4 h-4" />
                <span>+ New</span>
                <ChevronDown className="w-3.5 h-3.5 opacity-80" />
              </button>

              {showNewDropdown && (
                <div
                  className="absolute right-0 mt-2 w-48 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-xl z-50 py-1 font-medium text-xs text-slate-800 dark:text-slate-200 animate-in fade-in"
                  onClick={() => setShowNewDropdown(false)}
                >
                  <button
                    type="button"
                    className="w-full text-left px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center gap-2"
                    onClick={() => {
                      setActiveTab("tasks");
                      setShowAddInline(true);
                    }}
                  >
                    <Plus className="w-3.5 h-3.5 text-blue-500" /> New Task
                  </button>
                  <button
                    type="button"
                    className="w-full text-left px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center gap-2"
                    onClick={() => {
                      setActiveTab("materials");
                      setShowAddMaterial(true);
                    }}
                  >
                    <Package className="w-3.5 h-3.5 text-indigo-500" /> New Material
                  </button>
                  <Link
                    to={`/projects/${projectId}/documents/upload`}
                    className="block w-full text-left px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center gap-2"
                  >
                    <Upload className="w-3.5 h-3.5 text-emerald-500" /> Upload Document
                  </Link>
                  <Link
                    to="/query"
                    className="block w-full text-left px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center gap-2"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-cyan-500" /> New Query
                  </Link>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Row 2: Project Name & Status Badge */}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
            {project.name}
          </h2>
          <span className="tt-status-badge tt-status-badge-progress">
            {project.is_archived ? "Archived" : "In Progress"}
          </span>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Created {new Date(project.created_at).toLocaleDateString()}
          </span>
        </div>
      </header>

      {/* ── Jurisdiction Coverage Space ── */}
      {coverage && (
        <div
          className={`mb-6 rounded-2xl border p-5 shadow-sm text-sm ${
            coverage.is_covered
              ? "border-slate-200 bg-gradient-to-r from-white to-blue-50/40 dark:border-slate-700 dark:from-slate-800 dark:to-slate-800/90"
              : "border-amber-300 bg-amber-50 dark:border-amber-700/60 dark:bg-amber-900/20"
          }`}
        >
          <div className="flex flex-col sm:flex-row sm:items-start gap-4">
            {coverage.is_covered ? (
              <CheckCircle2 className="w-6 h-6 shrink-0 text-emerald-500 mt-0.5" />
            ) : (
              <AlertTriangle className="w-6 h-6 shrink-0 text-amber-500 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="text-xs font-extrabold uppercase tracking-widest text-slate-400 dark:text-slate-400">
                  Jurisdiction
                </span>
                <p className="text-base font-extrabold text-slate-900 dark:text-slate-100 uppercase tracking-wider">
                  {coverage.municipality || project.municipality || "Jurisdiction not set"}
                </p>
                {coverage.overlays?.map((ov) => (
                  <span
                    key={ov.id}
                    className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-indigo-100 dark:bg-indigo-900/60 text-indigo-800 dark:text-indigo-200"
                  >
                    {ov.name}
                  </span>
                ))}
              </div>
              <p className="text-xs sm:text-sm font-medium text-slate-600 dark:text-slate-300">
                This area is in our coverage zone, with{" "}
                <strong className="text-slate-900 dark:text-slate-100 font-bold">
                  {coverage.doc_count || coverage.document_count || documents.length || 12}
                </strong>{" "}
                amount of documents supporting.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0 pt-1 sm:pt-0">
              <Link
                to={`/projects/${projectId}/ordinance-petition`}
                className="tt-btn-secondary text-xs whitespace-nowrap"
              >
                Petition an ordinance
              </Link>
              <Link
                to={`/projects/${projectId}/petition`}
                className="tt-btn-secondary text-xs whitespace-nowrap"
              >
                Petition an overlay
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* ── 3 Summary Metric Cards ── */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* Card 1: Overall Progress */}
        <div className="bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
            Overall Progress
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-slate-100">
            {progressPercent}%
          </div>
          <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-2 my-2 overflow-hidden">
            <div
              className="bg-blue-600 dark:bg-blue-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-300 font-medium">
            {totalTasksCount > 0 ? `${completedTasks.length} of ${totalTasksCount} tasks complete` : "No tasks yet"}
          </p>
        </div>

        {/* Card 2: Target Budget (no expense tracking exists yet, so there's no honest "spent" figure to show) */}
        <div className="bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
            Target Budget
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-slate-100">
            {project.budget ? `$${budgetTotal.toLocaleString()}` : "Not set"}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-300 mt-3 font-medium">
            Entered during project kickoff
          </p>
        </div>

        {/* Card 3: Jurisdiction */}
        <div className="bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
            Jurisdiction
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-slate-100">
            {project.municipality || "Not set"}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-300 mt-3 font-medium">
            Used for permit rule lookups
          </p>
        </div>
      </section>

      {/* ── Sub Navigation Tab Bar ── */}
      <div className="border-b border-slate-200 dark:border-slate-700 mb-6 flex flex-wrap items-center gap-4 sm:gap-6 text-sm font-semibold">
        <button
          type="button"
          onClick={() => setActiveTab("tasks")}
          className={`pb-3 border-b-2 transition-colors ${
            activeTab === "tasks"
              ? "border-blue-600 text-blue-600 dark:text-blue-400"
              : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          Tasks ({openTasksCount})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("materials")}
          className={`pb-3 border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === "materials"
              ? "border-blue-600 text-blue-600 dark:text-blue-400"
              : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <Package className="w-4 h-4 text-indigo-500" />
          Materials & Supplies ({materials.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("uploaded")}
          className={`pb-3 border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === "uploaded"
              ? "border-blue-600 text-blue-600 dark:text-blue-400"
              : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <FileText className="w-4 h-4" />
          Uploaded Documents ({uploadedFiles.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("generated")}
          className={`pb-3 border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === "generated"
              ? "border-blue-600 text-blue-600 dark:text-blue-400"
              : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <Sparkles className="w-4 h-4 text-cyan-500" />
          Generated Documents ({generatedDocs.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("permit")}
          className={`pb-3 border-b-2 transition-colors ${
            activeTab === "permit"
              ? "border-blue-600 text-blue-600 dark:text-blue-400"
              : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          Permit Strategy
        </button>
      </div>

      {/* ── Tab 1: Tasks ── */}
      {activeTab === "tasks" && (
        <div className="bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
          {/* Add Inline Task Form */}
          {showAddInline && (
            <form onSubmit={handleAddInlineTask} className="tt-add-task-card mb-6">
              <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3">Add Task to {project.name}</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                <input
                  type="text"
                  placeholder="Task title"
                  value={newTaskTitle}
                  onChange={(e) => setNewTaskTitle(e.target.value)}
                  required
                  className="tt-input"
                />
                <select
                  value={newTaskCategory}
                  onChange={(e) => setNewTaskCategory(e.target.value)}
                  className="tt-select"
                >
                  <option value="PROCUREMENT">PROCUREMENT</option>
                  <option value="ELECTRICAL">ELECTRICAL</option>
                  <option value="DESIGN">DESIGN</option>
                  <option value="COMPLETION">COMPLETION</option>
                </select>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    className="tt-btn-secondary"
                    onClick={() => setShowAddInline(false)}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="tt-btn-primary">
                    Save Task
                  </button>
                </div>
              </div>
            </form>
          )}

          {/* Empty State */}
          {tasks.length === 0 && (
            <div className="py-8 text-center bg-slate-50/50 dark:bg-slate-900/40 rounded-xl border border-dashed border-slate-200 dark:border-slate-700 my-4">
              <CheckSquare className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-4">
                No tasks yet — add your first task to track milestones for {project.name}.
              </p>
              <button
                type="button"
                className="tt-btn-primary text-sm px-6 py-2.5 rounded-xl font-bold inline-flex items-center gap-2 shadow-sm hover:shadow transition-all"
                onClick={() => setShowAddInline(true)}
              >
                <Plus className="w-4 h-4 stroke-[2.5]" /> Add Task
              </button>
            </div>
          )}

          {/* Grouped Category Sections */}
          {projectTasks.map((cat) => (
            <div key={cat.category} className="mb-6 last:mb-0">
              <div className="text-xs font-extrabold uppercase tracking-wider text-slate-400 dark:text-slate-400 mb-3">
                {cat.category}
              </div>

              <ul className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {cat.tasks.map((task) => (
                  <li
                    key={task.id}
                    className="py-3 flex items-center justify-between gap-4 hover:bg-slate-50/60 dark:hover:bg-slate-700/50 px-2 rounded-lg transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => toggleOpenTask(task.id)}
                        className="w-5 h-5 rounded-full border-2 border-slate-300 dark:border-slate-500 hover:border-blue-600 flex items-center justify-center transition-colors"
                        aria-label={`Complete ${task.title}`}
                      />
                      <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        {task.title}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400 font-medium">
                      <span className="flex items-center">
                        <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${task.urgencyDot}`} />
                        {task.priority}
                      </span>
                      <span>• {task.dueDate}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {/* Completed Accordion Footer */}
          <div className="mt-8 pt-4 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setShowCompleted(!showCompleted)}
              className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors flex items-center gap-1.5"
            >
              {showCompleted ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              Completed ({completedTasks.length})
            </button>

            <button
              type="button"
              onClick={() => setShowAddInline(true)}
              className="text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" /> Add task
            </button>
          </div>

          {/* Completed Items Accordion List */}
          {showCompleted && (
            <ul className="mt-4 divide-y divide-slate-100 dark:divide-slate-700 bg-slate-50/50 dark:bg-slate-900/60 rounded-lg p-3">
              {completedTasks.map((t) => (
                <li key={t.id} className="py-2.5 flex items-center justify-between text-xs opacity-75">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => toggleCompletedTask(t.id)}
                      className="w-4 h-4 rounded-full bg-blue-600 border border-blue-600 flex items-center justify-center text-white"
                    >
                      <Check className="w-3 h-3 stroke-[3]" />
                    </button>
                    <span className="font-semibold text-slate-700 dark:text-slate-300 line-through">
                      {t.title}
                    </span>
                  </div>
                  <span className="text-slate-400 dark:text-slate-400">Done</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── Tab 2: Materials & Supplies ── */}
      {activeTab === "materials" && (
        <div className="bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Materials & Supplies</h3>
              <p className="text-xs text-slate-500 dark:text-slate-300">Track required hardware, tile, wiring, and construction supplies for {project.name}.</p>
            </div>
            <button
              type="button"
              className="tt-btn-primary flex items-center gap-1.5 text-xs self-start sm:self-auto"
              onClick={() => setShowAddMaterial(!showAddMaterial)}
            >
              <Plus className="w-4 h-4" />
              Add Material
            </button>
          </div>

          {/* Materials Metrics Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            <div className="p-4 bg-slate-50 dark:bg-slate-900/60 rounded-xl border border-slate-200 dark:border-slate-700">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 block mb-1">Total Estimated Cost</span>
              <span className="text-xl font-extrabold text-slate-900 dark:text-slate-100">${totalMaterialCost.toLocaleString()}</span>
            </div>
            <div className="p-4 bg-emerald-50/50 dark:bg-emerald-950/40 rounded-xl border border-emerald-200/60 dark:border-emerald-800/60">
              <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400 block mb-1">Purchased & Delivered</span>
              <span className="text-xl font-extrabold text-emerald-800 dark:text-emerald-300">${purchasedMaterialCost.toLocaleString()}</span>
            </div>
            <div className="p-4 bg-amber-50/50 dark:bg-amber-950/40 rounded-xl border border-amber-200/60 dark:border-amber-800/60">
              <span className="text-[11px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-400 block mb-1">On Order / Needed</span>
              <span className="text-xl font-extrabold text-amber-800 dark:text-amber-300">${(totalMaterialCost - purchasedMaterialCost).toLocaleString()}</span>
            </div>
          </div>

          {/* Inline Add Material Form */}
          {showAddMaterial && (
            <form onSubmit={handleAddMaterial} className="p-6 sm:p-8 bg-slate-50 dark:bg-slate-900/80 rounded-2xl border border-slate-200 dark:border-slate-700 mb-6 space-y-4 shadow-sm">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-2">New Material Record</h4>
              
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Material Name *
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. 1/2 in. Drywall Sheets"
                    value={newMatName}
                    onChange={(e) => setNewMatName(e.target.value)}
                    required
                    className="tt-input w-full px-3.5 py-2.5 text-xs"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Category
                  </label>
                  <select
                    value={newMatCat}
                    onChange={(e) => setNewMatCat(e.target.value)}
                    className="tt-select w-full px-3.5 py-2.5 text-xs"
                  >
                    <option value="Building Supplies">Building Supplies</option>
                    <option value="Electrical">Electrical</option>
                    <option value="Plumbing">Plumbing</option>
                    <option value="Finishings">Finishings</option>
                    <option value="Hardware">Hardware</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Supplier
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Home Depot"
                    value={newMatSupplier}
                    onChange={(e) => setNewMatSupplier(e.target.value)}
                    className="tt-input w-full px-3.5 py-2.5 text-xs"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Quantity
                  </label>
                  <input
                    type="number"
                    placeholder="1"
                    value={newMatQty}
                    onChange={(e) => setNewMatQty(e.target.value)}
                    className="tt-input w-full px-3.5 py-2.5 text-xs"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Unit Price ($)
                  </label>
                  <input
                    type="number"
                    placeholder="15.50"
                    value={newMatPrice}
                    onChange={(e) => setNewMatPrice(e.target.value)}
                    className="tt-input w-full px-3.5 py-2.5 text-xs"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Status
                  </label>
                  <select
                    value={newMatStatus}
                    onChange={(e) => setNewMatStatus(e.target.value)}
                    className="tt-select w-full px-3.5 py-2.5 text-xs"
                  >
                    <option value="Needed">Needed</option>
                    <option value="On Order">On Order</option>
                    <option value="Purchased">Purchased</option>
                    <option value="Delivered">Delivered</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3">
                <button type="button" className="tt-btn-secondary text-xs" onClick={() => setShowAddMaterial(false)}>
                  Cancel
                </button>
                <button type="submit" className="tt-btn-primary text-xs">
                  Save Material
                </button>
              </div>
            </form>
          )}

          {/* Materials Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                  <th className="pb-3 px-2">Item</th>
                  <th className="pb-3 px-2">Category</th>
                  <th className="pb-3 px-2">Supplier</th>
                  <th className="pb-3 px-2 text-right">Qty</th>
                  <th className="pb-3 px-2 text-right">Total</th>
                  <th className="pb-3 px-2 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700 font-medium text-slate-800 dark:text-slate-200">
                {materials.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-slate-500 dark:text-slate-400">
                      No materials added yet.
                    </td>
                  </tr>
                )}
                {materials.map((m) => {
                  const total = m.quantity * m.unitPrice;
                  let badgeStyle = "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300";
                  if (m.status === "Delivered") badgeStyle = "bg-blue-100 dark:bg-blue-900/60 text-blue-800 dark:text-blue-200";
                  if (m.status === "Purchased") badgeStyle = "bg-emerald-100 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-200";
                  if (m.status === "On Order") badgeStyle = "bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200";
                  if (m.status === "Needed") badgeStyle = "bg-rose-100 dark:bg-rose-900/60 text-rose-800 dark:text-rose-200";

                  return (
                    <tr key={m.id} className="hover:bg-slate-50/70 dark:hover:bg-slate-700/40 transition-colors">
                      <td className="py-3 px-2 font-semibold text-slate-900 dark:text-slate-100">{m.name}</td>
                      <td className="py-3 px-2 text-slate-500 dark:text-slate-400">{m.category}</td>
                      <td className="py-3 px-2 text-slate-500 dark:text-slate-400">{m.supplier}</td>
                      <td className="py-3 px-2 text-right">{m.quantity}</td>
                      <td className="py-3 px-2 text-right font-bold">${total.toLocaleString()}</td>
                      <td className="py-3 px-2 text-center">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${badgeStyle}`}>
                          {m.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Tab 3: Uploaded Documents ── */}
      {activeTab === "uploaded" && (
        <div className="bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Uploaded Documents & Files</h3>
              <p className="text-xs text-slate-500 dark:text-slate-300">Permits, inspection PDF documents, and 3D room scans uploaded for this project.</p>
            </div>
            <Link
              to={`/projects/${projectId}/documents/upload`}
              className="tt-btn-primary flex items-center gap-1.5 text-xs"
            >
              <Upload className="w-3.5 h-3.5" />
              Upload Document
            </Link>
          </div>

          {uploadedFiles.length === 0 && (
            <p className="text-sm text-slate-500 dark:text-slate-400 py-6 text-center">
              No documents uploaded yet.
            </p>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {uploadedFiles.map((file) => (
              <div key={file.id} className="p-4 border border-slate-200 dark:border-slate-700 rounded-xl hover:border-blue-400 dark:hover:border-blue-500 transition-colors flex items-start justify-between bg-white dark:bg-slate-900/60">
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <FileText className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{file.name}</h4>
                    <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">{file.type} • {file.date}</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="text-xs text-slate-500 dark:text-slate-400 hover:text-blue-600 p-1"
                  onClick={() => alert(`Opening ${file.name}`)}
                >
                  <Eye className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Tab 4: Generated Documents (AI LLM Instructions & Assets) ── */}
      {activeTab === "generated" && (
        <div className="bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Generated Documents & AI Assets</h3>
                <span className="px-2 py-0.5 text-[10px] font-bold text-cyan-700 dark:text-cyan-300 bg-cyan-50 dark:bg-cyan-950/60 border border-cyan-200 dark:border-cyan-800 rounded-full flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-cyan-500" /> AI Assistant
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
                Step-by-step instructions, compliance checklists, and material estimates generated automatically by the AI query engine.
              </p>
            </div>
          </div>

          {generatedDocs.length === 0 && (
            <p className="text-sm text-slate-500 dark:text-slate-400 py-6 text-center">
              No generated documents yet.
            </p>
          )}

          <div className="space-y-4">
            {generatedDocs.map((doc) => (
              <div
                key={doc.id}
                className="border border-slate-200 dark:border-slate-700 rounded-xl p-5 hover:border-cyan-400 transition-all bg-gradient-to-r from-white dark:from-slate-900 to-cyan-50/20 dark:to-cyan-950/20"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <FileCheck className="w-5 h-5 text-cyan-600 dark:text-cyan-400 flex-shrink-0" />
                    <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">{doc.title}</h4>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
                      {doc.type}
                    </span>
                    <span className="text-xs text-slate-400">{doc.date}</span>
                  </div>
                </div>

                <p className="text-xs text-slate-600 dark:text-slate-300 mb-3">{doc.summary}</p>

                <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-700">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      className="text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                      onClick={() => setSelectedDocPreview(doc)}
                    >
                      <Eye className="w-3.5 h-3.5" /> View Instructions
                    </button>

                    {doc.steps && (
                      <button
                        type="button"
                        className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 hover:underline flex items-center gap-1 bg-emerald-50 dark:bg-emerald-950/60 px-2 py-1 rounded-md border border-emerald-200 dark:border-emerald-800"
                        onClick={() => handleConvertStepsToTasks(doc)}
                      >
                        <Plus className="w-3.5 h-3.5" /> Convert Steps into Project Tasks
                      </button>
                    )}
                  </div>

                  <button
                    type="button"
                    className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 flex items-center gap-1"
                    onClick={() => {
                      navigator.clipboard.writeText(doc.content);
                      alert("Step-by-step instructions copied to clipboard!");
                    }}
                  >
                    <Download className="w-3.5 h-3.5" /> Copy Text
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Modal Preview Dialog for Generated Document Instructions */}
          {selectedDocPreview && (
            <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
              <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-700 mb-4">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-cyan-500" />
                    <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{selectedDocPreview.title}</h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedDocPreview(null)}
                    className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 font-bold"
                  >
                    ✕
                  </button>
                </div>

                <div className="bg-slate-50 dark:bg-slate-900 p-4 rounded-xl text-xs font-mono text-slate-800 dark:text-slate-200 whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto mb-4 border border-slate-200 dark:border-slate-700">
                  {selectedDocPreview.content}
                </div>

                <div className="flex items-center justify-between">
                  {selectedDocPreview.steps ? (
                    <button
                      type="button"
                      className="tt-btn-primary text-xs flex items-center gap-1 bg-emerald-600 hover:bg-emerald-700 border-emerald-600"
                      onClick={() => {
                        handleConvertStepsToTasks(selectedDocPreview);
                        setSelectedDocPreview(null);
                      }}
                    >
                      <Plus className="w-3.5 h-3.5" /> Add Steps to Tasks List
                    </button>
                  ) : <div />}

                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="tt-btn-secondary text-xs"
                      onClick={() => setSelectedDocPreview(null)}
                    >
                      Close
                    </button>
                    <button
                      type="button"
                      className="tt-btn-primary text-xs"
                      onClick={() => {
                        navigator.clipboard.writeText(selectedDocPreview.content);
                        alert("Copied to clipboard!");
                      }}
                    >
                      Copy Instructions
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Tab 5: Permit Strategy ── */}
      {activeTab === "permit" && (
        <div className="bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-2">Permit Strategy & Pull Order</h3>
          {permitStrategy && permitStrategy.permits?.length > 0 ? (
            <div>
              <p className="text-sm text-slate-600 dark:text-slate-300 mb-4 font-medium">
                Sequence: {permitStrategy.sequence.join(" → ")}
              </p>
              <ul className="space-y-2 mb-4">
                {permitStrategy.permits.map((p) => (
                  <li key={p} className="p-3 bg-slate-50 dark:bg-slate-900/60 rounded-lg text-sm font-semibold text-slate-800 dark:text-slate-200 flex justify-between items-center">
                    <span>{p}</span>
                    <span className="text-slate-500 dark:text-slate-400">~${permitStrategy.fee_breakdown?.[p] || "150"}</span>
                  </li>
                ))}
              </ul>
              <div className="p-3 bg-slate-100 dark:bg-slate-900/80 rounded-lg text-sm font-bold text-slate-900 dark:text-slate-100 flex justify-between items-center border border-slate-200 dark:border-slate-700">
                <span>Total Estimated Permit Fees</span>
                <span>~${permitStrategy.estimated_fees_usd}</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Permit strategy requires completing municipal jurisdiction checks for {project.municipality || "this project"}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
