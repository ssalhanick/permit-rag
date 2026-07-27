import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useProject } from "../ProjectContext.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import {
  fetchProjectRoomScans,
  fetchQueryHistory,
  fetchProjectDocuments,
  fetchPermitStrategy,
} from "../../api.js";
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
  ArrowRight
} from "lucide-react";

export default function ProjectDashboardPage() {
  const { project, projectId } = useProject();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState("tasks");
  const [scans, setScans] = useState([]);
  const [queries, setQueries] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [permitStrategy, setPermitStrategy] = useState(null);
  const [selectedDocPreview, setSelectedDocPreview] = useState(null);

  // Grouped task categories for this specific project
  const [projectTasks, setProjectTasks] = useState([
    {
      category: "PROCUREMENT",
      tasks: [
        { id: 101, title: "Get three quotes for cabinet install", priority: "High", urgencyDot: "bg-rose-500", dueDate: "2d overdue", completed: false },
        { id: 102, title: "Order countertop samples", priority: "Medium", urgencyDot: "bg-amber-500", dueDate: "1d", completed: false },
      ]
    },
    {
      category: "ELECTRICAL",
      tasks: [
        { id: 103, title: "Confirm electrician start date", priority: "High", urgencyDot: "bg-amber-500", dueDate: "3d", completed: false },
      ]
    },
    {
      category: "DESIGN",
      tasks: [
        { id: 104, title: "Drywall Patching & Sanding", priority: "Medium", urgencyDot: "bg-rose-500", dueDate: "5d", completed: false },
      ]
    },
    {
      category: "COMPLETION",
      tasks: [
        { id: 105, title: "Schedule Plumbing Rough-in Inspection", priority: "High", urgencyDot: "bg-sky-500", dueDate: "19d", completed: false },
      ]
    }
  ]);

  const [completedTasks, setCompletedTasks] = useState([
    { id: 201, title: "Review permit requirements", priority: "High", completed: true },
    { id: 202, title: "Order tile samples for backsplash", priority: "Medium", completed: true },
    { id: 203, title: "Disconnect old appliance lines", priority: "High", completed: true },
    { id: 204, title: "Submit electrical permit application", priority: "High", completed: true }
  ]);

  // Materials & Supplies List for this project
  const [materials, setMaterials] = useState([
    { id: "mat-1", name: "12/2 NM-B Wire (250 ft roll)", category: "Electrical", quantity: 2, unitPrice: 145, supplier: "Home Depot", status: "Delivered" },
    { id: "mat-2", name: "1/2\" Type X Fire-Rated Drywall (4x8)", category: "Building Supplies", quantity: 24, unitPrice: 18.5, supplier: "Lowe's", status: "Purchased" },
    { id: "mat-3", name: "White Ceramic Subway Tile (3\"x6\")", category: "Finishings", quantity: 15, unitPrice: 28.0, supplier: "Floor & Decor", status: "On Order" },
    { id: "mat-4", name: "Polymer-Modified Thin-Set Mortar", category: "Finishings", quantity: 4, unitPrice: 34.0, supplier: "Home Depot", status: "Needed" },
    { id: "mat-5", name: "AFCI/GFCI Dual Function Breaker 20A", category: "Electrical", quantity: 6, unitPrice: 52.0, supplier: "Electrical Supply Direct", status: "Purchased" },
  ]);

  const [showAddMaterial, setShowAddMaterial] = useState(false);
  const [newMatName, setNewMatName] = useState("");
  const [newMatCat, setNewMatCat] = useState("Building Supplies");
  const [newMatQty, setNewMatQty] = useState(1);
  const [newMatPrice, setNewMatPrice] = useState(25);
  const [newMatSupplier, setNewMatSupplier] = useState("Home Depot");
  const [newMatStatus, setNewMatStatus] = useState("Needed");

  // AI LLM Generated Documents for this project
  const [generatedDocs, setGeneratedDocs] = useState([
    {
      id: "gen-doc-1",
      title: "Step-by-Step Electrical Panel Rough-In Guide",
      type: "Instructions & Steps",
      date: "Jul 26, 2026",
      summary: "Detailed 8-step guide for conduit sizing, wire gauge requirements, breaker box mounting, and neutral bar bonding per 2026 NEC standards.",
      content: `1. Turn off main power service disconnect prior to opening panel cover.\n2. Mount subpanel securely to wall framing using minimum 1/4" lag screws.\n3. Pull 4-wire feed (L1, L2, Neutral, Ground) through code-approved conduit.\n4. Connect neutral wire directly to insulated neutral bus bar.\n5. Keep grounding wire isolated on grounding bar bonded to enclosure.\n6. Install AFCI/GFCI dual-function breakers for all kitchen and bath branch circuits.\n7. Label all circuit switches clearly inside dead-front panel door.\n8. Request rough-in electrical inspection from municipality prior to drywall cover.`,
      steps: [
        "Turn off main power service disconnect prior to opening panel cover",
        "Mount subpanel securely to wall framing using minimum 1/4 inch lag screws",
        "Pull 4-wire feed (L1, L2, Neutral, Ground) through code-approved conduit",
        "Connect neutral wire directly to insulated neutral bus bar",
        "Keep grounding wire isolated on grounding bar bonded to enclosure",
        "Install AFCI/GFCI dual-function breakers for kitchen/bath branch circuits",
        "Label all circuit switches clearly inside dead-front panel door",
        "Request rough-in electrical inspection prior to drywall cover"
      ]
    },
    {
      id: "gen-doc-2",
      title: "Municipal Permit Compliance Inspection Checklist",
      type: "Checklist",
      date: "Jul 24, 2026",
      summary: "City inspector pre-check list covering plumbing clearance, outlet spacing, smoke detector wiring, and structural load verification.",
      content: `[ ] Plumbing vent stack extends minimum 6" above roofline.\n[ ] Outlets spaced no more than 12 feet apart on continuous wall runs.\n[ ] Hardwired interconnected smoke/CO detectors active on all floors.\n[ ] Structural header beam calculations verified for load-bearing wall removal.\n[ ] Egress window dimensions meet minimum 5.7 sq ft net opening area.`,
      steps: [
        "Verify plumbing vent stack extends minimum 6 inches above roofline",
        "Check outlets spaced no more than 12 feet apart on wall runs",
        "Test hardwired interconnected smoke/CO detectors on all floors",
        "Verify structural header beam load calculations with inspector",
        "Measure egress window dimensions for 5.7 sq ft net opening"
      ]
    },
    {
      id: "gen-doc-3",
      title: "Scope of Work & Materials Cost Breakdown",
      type: "Estimate & Scope",
      date: "Jul 20, 2026",
      summary: "AI estimated quantity breakdown for drywall sheets, 12/2 Romex wiring, tile adhesive, and fixture allowances.",
      content: `• Drywall (1/2" Type X Fire-rated): 48 sheets @ $18.50 = $888.00\n• 12/2 NM-B Wire (250 ft roll): 2 rolls @ $145.00 = $290.00\n• Thinset Mortar & Polymer Grout: $240.00\n• Electrical Box Enclosures & Tamper-Resistant Outlets: $185.00\n• Estimated Material Subtotal: $1,603.00 (excl. sales tax)`,
    },
  ]);

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

  // Compute tasks metrics dynamically
  const openTasksCount = projectTasks.reduce((acc, cat) => acc + cat.tasks.length, 0);
  const totalTasksCount = openTasksCount + completedTasks.length;
  const progressPercent = totalTasksCount > 0 ? Math.round((completedTasks.length / totalTasksCount) * 100) : (project.progress || 62);

  // Compute live budget metrics
  const spentAmount = project.spent || 11470;
  const budgetTotal = project.budget || 18500;
  const remainingBudget = Math.max(budgetTotal - spentAmount, 0);
  const spentPercent = budgetTotal > 0 ? Math.round((spentAmount / budgetTotal) * 100) : 62;

  // Compute materials metrics
  const totalMaterialCost = materials.reduce((acc, m) => acc + m.unitPrice * m.quantity, 0);
  const purchasedMaterialCost = materials
    .filter((m) => m.status === "Purchased" || m.status === "Delivered")
    .reduce((acc, m) => acc + m.unitPrice * m.quantity, 0);

  const toggleOpenTask = (catIndex, taskId) => {
    const updated = [...projectTasks];
    const targetCategory = updated[catIndex];
    const taskIndex = targetCategory.tasks.findIndex((t) => t.id === taskId);
    if (taskIndex !== -1) {
      const [task] = targetCategory.tasks.splice(taskIndex, 1);
      setCompletedTasks([{ ...task, completed: true }, ...completedTasks]);
      setProjectTasks(updated);
    }
  };

  const toggleCompletedTask = (taskId) => {
    const taskIndex = completedTasks.findIndex((t) => t.id === taskId);
    if (taskIndex !== -1) {
      const [task] = completedTasks.splice(taskIndex, 1);
      setCompletedTasks([...completedTasks]);

      const updated = [...projectTasks];
      updated[0].tasks.push({ ...task, completed: false, urgencyDot: "bg-sky-500", dueDate: "Soon" });
      setProjectTasks(updated);
    }
  };

  const handleAddInlineTask = (e) => {
    e.preventDefault();
    if (!newTaskTitle.trim()) return;
    const newTask = {
      id: Date.now(),
      title: newTaskTitle.trim(),
      priority: "Medium",
      urgencyDot: "bg-sky-500",
      dueDate: "Soon",
      completed: false,
    };
    const updated = projectTasks.map((cat) =>
      cat.category === newTaskCategory
        ? { ...cat, tasks: [...cat.tasks, newTask] }
        : cat
    );
    setProjectTasks(updated);
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
      id: Date.now() + idx,
      title: stepText,
      priority: "High",
      urgencyDot: "bg-blue-500",
      dueDate: "AI Generated",
      completed: false,
    }));

    const updated = projectTasks.map((cat) =>
      cat.category === "PROCUREMENT" || cat.category === "ELECTRICAL"
        ? { ...cat, tasks: [...cat.tasks, ...newTasks] }
        : cat
    );

    setProjectTasks(updated);
    setActiveTab("tasks");
    alert(`Successfully added ${newTasks.length} AI generated tasks to your project task list!`);
  };

  // Combining uploaded files & room scans for the Uploaded Documents tab
  const uploadedFiles = [
    ...documents.map((d) => ({ id: d.id, name: d.doc_id || d.filename || "Building Code Doc", type: d.doc_type || "PDF Document", date: "Uploaded" })),
    ...scans.map((s) => ({ id: s.id, name: `${s.room_label || "Room"} 3D Mesh Scan`, type: "3D Scan File", date: "Scanned" })),
    { id: "up-1", name: "Approved Building Permit Application.pdf", type: "PDF Document", date: "Jun 12, 2026" },
    { id: "up-2", name: "Contractor Site Inspection Notes.pdf", type: "PDF Document", date: "Jun 18, 2026" },
    { id: "up-3", name: "Main Electrical Panel Wiring Diagram.png", type: "Image Attachment", date: "Jul 2, 2026" },
  ];

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6">
      {/* ── Breadcrumbs ── */}
      <nav className="text-xs font-semibold text-slate-500 mb-2 flex items-center gap-1.5">
        <Link to="/projects" className="hover:text-blue-600 transition-colors">
          Projects
        </Link>
        <span>/</span>
        <span className="text-slate-900">{project.name}</span>
      </nav>

      {/* ── Top Header Section ── */}
      <header className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              {project.name}
            </h1>
            <span className="tt-status-badge tt-status-badge-progress">
              {project.is_archived ? "Archived" : "In Progress"}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            {project.contractor || "Marta's Remodeling Co."} • Started {project.startDate || "Jun 1, 2026"} • Due {project.dueDate || "Sep 14, 2026"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to={`/projects/${projectId}/settings`}
            className="tt-btn-secondary flex items-center gap-1.5 text-xs"
          >
            <SettingsIcon className="w-4 h-4 text-slate-400" />
            Settings
          </Link>
          <button
            type="button"
            className="tt-btn-primary flex items-center gap-1.5 text-xs"
            onClick={() => setShowAddInline(!showAddInline)}
          >
            <Plus className="w-4 h-4" />
            Add task
          </button>
        </div>
      </header>

      {/* ── 3 Summary Metric Cards ── */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* Card 1: Overall Progress */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
            Overall Progress
          </div>
          <div className="text-2xl font-extrabold text-slate-900">
            {progressPercent}%
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2 my-2 overflow-hidden">
            <div
              className="bg-blue-600 h-full rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="text-xs text-slate-500 font-medium">
            {completedTasks.length} of {totalTasksCount} tasks complete
          </div>
        </div>

        {/* Card 2: Spent */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
            Spent
          </div>
          <div className="text-2xl font-extrabold text-slate-900">
            ${spentAmount.toLocaleString()}
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2 my-2 overflow-hidden">
            <div
              className="bg-sky-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${spentPercent}%` }}
            />
          </div>
          <div className="text-xs text-slate-500 font-medium">
            of ${budgetTotal.toLocaleString()} budget ({spentPercent}% used)
          </div>
        </div>

        {/* Card 3: Remaining */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
            Remaining Budget
          </div>
          <div className="text-2xl font-extrabold text-emerald-600">
            ${remainingBudget.toLocaleString()}
          </div>
          <p className="text-xs text-slate-500 mt-3 font-medium">
            Project jurisdiction: {project.municipality || "Local"}
          </p>
        </div>
      </section>

      {/* ── Sub Navigation Tab Bar ── */}
      <div className="border-b border-slate-200 mb-6 flex flex-wrap items-center gap-4 sm:gap-6 text-sm font-semibold">
        <button
          type="button"
          onClick={() => setActiveTab("tasks")}
          className={`pb-3 border-b-2 transition-colors ${
            activeTab === "tasks"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Tasks ({openTasksCount})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("materials")}
          className={`pb-3 border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === "materials"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
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
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
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
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
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
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Permit Strategy
        </button>
      </div>

      {/* ── Tab 1: Tasks ── */}
      {activeTab === "tasks" && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          {/* Add Inline Task Form */}
          {showAddInline && (
            <form onSubmit={handleAddInlineTask} className="tt-add-task-card mb-6">
              <h4 className="text-sm font-semibold text-slate-800 mb-3">Add Task to {project.name}</h4>
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

          {/* Grouped Category Sections */}
          {projectTasks.map((cat, catIdx) => (
            <div key={cat.category} className="mb-6 last:mb-0">
              <div className="text-xs font-extrabold uppercase tracking-wider text-slate-400 mb-3">
                {cat.category}
              </div>

              <ul className="divide-y divide-slate-100">
                {cat.tasks.map((task) => (
                  <li
                    key={task.id}
                    className="py-3 flex items-center justify-between gap-4 hover:bg-slate-50/60 px-2 rounded-lg transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => toggleOpenTask(catIdx, task.id)}
                        className="w-5 h-5 rounded-full border-2 border-slate-300 hover:border-blue-600 flex items-center justify-center transition-colors"
                        aria-label={`Complete ${task.title}`}
                      />
                      <span className="text-sm font-semibold text-slate-900">
                        {task.title}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs text-slate-500 font-medium">
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
          <div className="mt-8 pt-4 border-t border-slate-100 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setShowCompleted(!showCompleted)}
              className="text-xs font-bold uppercase tracking-wider text-slate-500 hover:text-blue-600 transition-colors flex items-center gap-1.5"
            >
              {showCompleted ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              Completed ({completedTasks.length})
            </button>

            <button
              type="button"
              onClick={() => setShowAddInline(true)}
              className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" /> Add task
            </button>
          </div>

          {/* Completed Items Accordion List */}
          {showCompleted && (
            <ul className="mt-4 divide-y divide-slate-100 bg-slate-50/50 rounded-lg p-3">
              {completedTasks.map((t) => (
                <li key={t.id} className="py-2.5 flex items-center justify-between text-xs opacity-60">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => toggleCompletedTask(t.id)}
                      className="w-4 h-4 rounded-full bg-blue-600 border border-blue-600 flex items-center justify-center text-white"
                    >
                      <Check className="w-3 h-3 stroke-[3]" />
                    </button>
                    <span className="font-semibold text-slate-700 line-through">
                      {t.title}
                    </span>
                  </div>
                  <span className="text-slate-400">Done</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── Tab 2: Materials & Supplies ── */}
      {activeTab === "materials" && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h3 className="text-base font-bold text-slate-900">Materials & Supplies</h3>
              <p className="text-xs text-slate-500">Track required hardware, tile, wiring, and construction supplies for {project.name}.</p>
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
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block mb-1">Total Estimated Cost</span>
              <span className="text-xl font-extrabold text-slate-900">${totalMaterialCost.toLocaleString()}</span>
            </div>
            <div className="p-4 bg-emerald-50/50 rounded-xl border border-emerald-200/60">
              <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-700 block mb-1">Purchased & Delivered</span>
              <span className="text-xl font-extrabold text-emerald-800">${purchasedMaterialCost.toLocaleString()}</span>
            </div>
            <div className="p-4 bg-amber-50/50 rounded-xl border border-amber-200/60">
              <span className="text-[11px] font-bold uppercase tracking-wider text-amber-700 block mb-1">On Order / Needed</span>
              <span className="text-xl font-extrabold text-amber-800">${(totalMaterialCost - purchasedMaterialCost).toLocaleString()}</span>
            </div>
          </div>

          {/* Inline Add Material Form */}
          {showAddMaterial && (
            <form onSubmit={handleAddMaterial} className="p-4 bg-slate-50 rounded-xl border border-slate-200 mb-6 space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">New Material Record</h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <input
                  type="text"
                  placeholder="Material name"
                  value={newMatName}
                  onChange={(e) => setNewMatName(e.target.value)}
                  required
                  className="tt-input text-xs"
                />
                <select
                  value={newMatCat}
                  onChange={(e) => setNewMatCat(e.target.value)}
                  className="tt-select text-xs"
                >
                  <option value="Building Supplies">Building Supplies</option>
                  <option value="Electrical">Electrical</option>
                  <option value="Plumbing">Plumbing</option>
                  <option value="Finishings">Finishings</option>
                  <option value="Hardware">Hardware</option>
                </select>
                <input
                  type="text"
                  placeholder="Supplier (e.g. Home Depot)"
                  value={newMatSupplier}
                  onChange={(e) => setNewMatSupplier(e.target.value)}
                  className="tt-input text-xs"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <input
                  type="number"
                  placeholder="Qty"
                  value={newMatQty}
                  onChange={(e) => setNewMatQty(e.target.value)}
                  className="tt-input text-xs"
                />
                <input
                  type="number"
                  placeholder="Unit price ($)"
                  value={newMatPrice}
                  onChange={(e) => setNewMatPrice(e.target.value)}
                  className="tt-input text-xs"
                />
                <select
                  value={newMatStatus}
                  onChange={(e) => setNewMatStatus(e.target.value)}
                  className="tt-select text-xs"
                >
                  <option value="Needed">Needed</option>
                  <option value="On Order">On Order</option>
                  <option value="Purchased">Purchased</option>
                  <option value="Delivered">Delivered</option>
                </select>
              </div>

              <div className="flex justify-end gap-2 pt-2">
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
                <tr className="border-b border-slate-200 text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                  <th className="pb-3 px-2">Item</th>
                  <th className="pb-3 px-2">Category</th>
                  <th className="pb-3 px-2">Supplier</th>
                  <th className="pb-3 px-2 text-right">Qty</th>
                  <th className="pb-3 px-2 text-right">Total</th>
                  <th className="pb-3 px-2 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium text-slate-800">
                {materials.map((m) => {
                  const total = m.quantity * m.unitPrice;
                  let badgeStyle = "bg-slate-100 text-slate-600";
                  if (m.status === "Delivered") badgeStyle = "bg-blue-100 text-blue-800";
                  if (m.status === "Purchased") badgeStyle = "bg-emerald-100 text-emerald-800";
                  if (m.status === "On Order") badgeStyle = "bg-amber-100 text-amber-800";
                  if (m.status === "Needed") badgeStyle = "bg-rose-100 text-rose-800";

                  return (
                    <tr key={m.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 px-2 font-semibold text-slate-900">{m.name}</td>
                      <td className="py-3 px-2 text-slate-500">{m.category}</td>
                      <td className="py-3 px-2 text-slate-500">{m.supplier}</td>
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
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-base font-bold text-slate-900">Uploaded Documents & Files</h3>
              <p className="text-xs text-slate-500">Permits, inspection PDF documents, and 3D room scans uploaded for this project.</p>
            </div>
            <Link to="/upload" className="tt-btn-primary flex items-center gap-1.5 text-xs">
              <Upload className="w-3.5 h-3.5" />
              Upload Document
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {uploadedFiles.map((file) => (
              <div key={file.id} className="p-4 border border-slate-200 rounded-xl hover:border-blue-400 transition-colors flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <FileText className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-900">{file.name}</h4>
                    <span className="text-xs text-slate-500 font-medium">{file.type} • {file.date}</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="text-xs text-slate-500 hover:text-blue-600 p-1"
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
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-slate-900">Generated Documents & AI Assets</h3>
                <span className="px-2 py-0.5 text-[10px] font-bold text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-cyan-500" /> AI Assistant
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Step-by-step instructions, compliance checklists, and material estimates generated automatically by the AI query engine.
              </p>
            </div>
          </div>

          <div className="space-y-4">
            {generatedDocs.map((doc) => (
              <div
                key={doc.id}
                className="border border-slate-200 rounded-xl p-5 hover:border-cyan-400 transition-all bg-gradient-to-r from-white to-cyan-50/20"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <FileCheck className="w-5 h-5 text-cyan-600 flex-shrink-0" />
                    <h4 className="text-sm font-bold text-slate-900">{doc.title}</h4>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                      {doc.type}
                    </span>
                    <span className="text-xs text-slate-400">{doc.date}</span>
                  </div>
                </div>

                <p className="text-xs text-slate-600 mb-3">{doc.summary}</p>

                <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
                      onClick={() => setSelectedDocPreview(doc)}
                    >
                      <Eye className="w-3.5 h-3.5" /> View Instructions
                    </button>

                    {doc.steps && (
                      <button
                        type="button"
                        className="text-xs font-semibold text-emerald-600 hover:text-emerald-800 flex items-center gap-1 bg-emerald-50 px-2 py-1 rounded-md border border-emerald-200"
                        onClick={() => handleConvertStepsToTasks(doc)}
                      >
                        <Plus className="w-3.5 h-3.5" /> Convert Steps into Project Tasks
                      </button>
                    )}
                  </div>

                  <button
                    type="button"
                    className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"
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
              <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-200">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-cyan-500" />
                    <h3 className="text-base font-bold text-slate-900">{selectedDocPreview.title}</h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedDocPreview(null)}
                    className="text-slate-400 hover:text-slate-600 font-bold"
                  >
                    ✕
                  </button>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl text-xs font-mono text-slate-800 whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto mb-4 border border-slate-200">
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
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h3 className="text-base font-bold text-slate-900 mb-2">Permit Strategy & Pull Order</h3>
          {permitStrategy && permitStrategy.permits?.length > 0 ? (
            <div>
              <p className="text-sm text-slate-600 mb-4 font-medium">
                Sequence: {permitStrategy.sequence.join(" → ")}
              </p>
              <ul className="space-y-2 mb-4">
                {permitStrategy.permits.map((p) => (
                  <li key={p} className="p-3 bg-slate-50 rounded-lg text-sm font-semibold text-slate-800 flex justify-between">
                    <span>{p}</span>
                    <span className="text-slate-500">~${permitStrategy.fee_breakdown?.[p] || "150"}</span>
                  </li>
                ))}
              </ul>
              <p className="text-sm font-bold text-slate-900">
                Total Estimated Permit Fees: ~${permitStrategy.estimated_fees_usd}
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              Permit strategy requires completing municipal jurisdiction checks for {project.municipality || "this project"}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
