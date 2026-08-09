import React, { useState } from "react";
import { Link } from "react-router-dom";
import {
  Building2,
  FileText,
  ExternalLink,
  Sparkles,
  ShieldCheck,
  Tag,
  CheckCircle2,
  Calendar,
  Layers,
  Search,
  BookOpen,
  MapPin,
  Flame,
  Zap,
  CheckSquare,
  DollarSign,
  AlertCircle,
  Clock,
  ArrowRight,
  Send
} from "lucide-react";
import { getJurisdictionById } from "../../data/coverageCatalogData.js";

/**
 * JurisdictionSpotlight
 * Visual showcase displaying all regulatory documents, local amendments,
 * AHJ contact links, and interactive AI query triggers for the selected jurisdiction.
 */
export default function JurisdictionSpotlight({
  jurisdictionId = "dallas",
  onTagClick,
  onRequestPetition,
}) {
  const [docFilterCategory, setDocFilterCategory] = useState("all");
  const [docSearchQuery, setDocSearchQuery] = useState("");

  const jurisdiction = getJurisdictionById(jurisdictionId);

  if (!jurisdiction) {
    return (
      <div className="p-8 text-center bg-card rounded-2xl border border-border shadow-sm">
        <Building2 className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
        <h3 className="text-lg font-bold">Select a Jurisdiction</h3>
        <p className="text-sm text-muted-foreground">
          Click on any node on the coverage map or choose from the list to view its complete document catalog.
        </p>
      </div>
    );
  }

  const isPipeline = jurisdiction.status === "pipeline";
  const documents = jurisdiction.documents || [];

  // Filter documents by category & search
  const filteredDocuments = documents.filter((doc) => {
    if (docFilterCategory !== "all") {
      const matchCat =
        doc.category.toLowerCase().includes(docFilterCategory.toLowerCase()) ||
        doc.doc_type.toLowerCase().includes(docFilterCategory.toLowerCase());
      if (!matchCat) return false;
    }

    if (docSearchQuery.trim()) {
      const query = docSearchQuery.toLowerCase();
      const matchText =
        doc.title.toLowerCase().includes(query) ||
        doc.notes.toLowerCase().includes(query) ||
        doc.subject_tags.some((t) => t.toLowerCase().includes(query));
      if (!matchText) return false;
    }

    return true;
  });

  // Category badge helper
  const getCategoryColor = (docType = "", category = "") => {
    const combined = `${docType} ${category}`.toLowerCase();
    if (combined.includes("fire")) return "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20";
    if (combined.includes("zoning") || combined.includes("land-use")) return "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20";
    if (combined.includes("building") || combined.includes("construction")) return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20";
    if (combined.includes("energy") || combined.includes("iecc")) return "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/20";
    if (combined.includes("checklist")) return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20";
    if (combined.includes("fee") || combined.includes("schedule")) return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20";
    if (combined.includes("access") || combined.includes("ada") || combined.includes("tas")) return "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20";
    return "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20";
  };

  const getCategoryIcon = (docType = "", category = "") => {
    const combined = `${docType} ${category}`.toLowerCase();
    if (combined.includes("fire")) return <Flame className="w-3.5 h-3.5" />;
    if (combined.includes("energy") || combined.includes("electrical")) return <Zap className="w-3.5 h-3.5" />;
    if (combined.includes("checklist")) return <CheckSquare className="w-3.5 h-3.5" />;
    if (combined.includes("fee")) return <DollarSign className="w-3.5 h-3.5" />;
    return <FileText className="w-3.5 h-3.5" />;
  };

  return (
    <div className="bg-card rounded-2xl border border-border shadow-md overflow-hidden transition-all">
      {/* ── Jurisdiction Header Banner ── */}
      <div className="p-6 sm:p-8 bg-gradient-to-r from-secondary/40 via-card to-secondary/20 border-b border-border space-y-4">
        {/* 1. Badges Row */}
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 inline-flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
            Active Coverage
          </span>
          {jurisdiction.state && (
            <span className="text-xs font-semibold text-muted-foreground">
              {jurisdiction.county || jurisdiction.state}
            </span>
          )}
        </div>

        {/* 2. City Title */}
        <h2 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight flex items-center gap-2.5">
          <Building2 className="w-7 h-7 text-blue-500" />
          <span>{jurisdiction.fullName || jurisdiction.name}</span>
        </h2>

        {/* 3. Metadata Row (Population) */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          {jurisdiction.population && (
            <span>
              Population: <strong className="text-foreground">{jurisdiction.population}</strong>
            </span>
          )}
        </div>

        {/* 4. Action Buttons — Dedicated Full-Width Row (Not inline with city name) */}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          {jurisdiction.ahj?.portalUrl && (
            <a
              href={jurisdiction.ahj.portalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="tt-btn-secondary text-xs px-3.5 py-2 flex items-center gap-2 shadow-sm"
            >
              <span>Official AHJ Portal</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}

          {!isPipeline ? (
            <Link
              to={`/query?municipality=${jurisdiction.id}`}
              className="tt-btn-primary text-xs px-4 py-2 flex items-center gap-2 shadow-md shadow-blue-500/20"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Query {jurisdiction.name} Code</span>
            </Link>
          ) : (
            <button
              type="button"
              onClick={() => onRequestPetition && onRequestPetition(jurisdiction)}
              className="tt-btn-primary bg-amber-600 hover:bg-amber-700 text-xs px-4 py-2 flex items-center gap-2 shadow-md"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Petition This City</span>
            </button>
          )}
        </div>

        {/* 5. Key Highlights (No bullets) */}
        {jurisdiction.highlights && jurisdiction.highlights.length > 0 && (
          <div className="pt-3 border-t border-border/80">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              Key Regulatory Features & Local Nuances:
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {jurisdiction.highlights.map((highlight, idx) => (
                <div key={idx} className="text-xs text-foreground/90 py-0.5">
                  {highlight}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Pipeline Expansion Notice (If in pipeline) ── */}
      {isPipeline ? (
        <div className="p-8 text-center space-y-4">
          <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl max-w-lg mx-auto space-y-2">
            <AlertCircle className="w-8 h-8 text-amber-500 mx-auto" />
            <h3 className="text-base font-bold text-foreground">Ingestion Pipeline Queued</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {jurisdiction.note || "This municipality is queued for full document harvesting and RAG chunk indexing in our upcoming Wave release."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onRequestPetition && onRequestPetition(jurisdiction)}
            className="tt-btn-primary text-xs px-6 py-2.5 inline-flex items-center gap-2 shadow-md"
          >
            <Send className="w-4 h-4" />
            <span>Fast-Track Ingestion for {jurisdiction.name}</span>
          </button>
        </div>
      ) : (
        /* ── Documents Catalog Explorer ── */
        <div className="p-6 sm:p-8 space-y-6">
          {/* Section Subheader & Search / Filter Controls */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-blue-500" />
                Available Regulatory Documents ({documents.length})
              </h3>
              <p className="text-xs text-muted-foreground">
                All codes, checklists, and ordinances are parsed, chunked, and vector-indexed for instant citation.
              </p>
            </div>

            {/* Quick Search inside Jurisdiction */}
            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Filter this city's codes..."
                value={docSearchQuery}
                onChange={(e) => setDocSearchQuery(e.target.value)}
                className="tt-input w-full pl-9 pr-3 py-1.5 text-xs rounded-xl"
              />
            </div>
          </div>

          {/* Category Filter Pills */}
          <div className="flex flex-wrap items-center gap-1.5 border-b border-border pb-3">
            {[
              { id: "all", label: `All Codes (${documents.length})` },
              { id: "building", label: "Building Code" },
              { id: "zoning", label: "Zoning & Land Use" },
              { id: "fire", label: "Fire & Safety" },
              { id: "energy", label: "Energy (IECC)" },
              { id: "checklist", label: "Checklists & Fees" },
              { id: "statute", label: "Statutes & Rules" },
            ].map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => setDocFilterCategory(cat.id)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                  docFilterCategory === cat.id
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          {/* Documents Grid — Single Column Layout for 33% container readability */}
          <div className="grid grid-cols-1 gap-4 max-h-[640px] overflow-y-auto pr-1">
            {filteredDocuments.length === 0 ? (
              <div className="col-span-full py-8 text-center text-muted-foreground text-xs">
                No regulatory documents matched your filter. Try clearing your search term.
              </div>
            ) : (
              filteredDocuments.map((doc) => (
                <div
                  key={doc.doc_id}
                  className="p-5 bg-card rounded-xl border border-border hover:border-blue-500/40 hover:shadow-md transition-all flex flex-col justify-between space-y-4 group"
                >
                  <div className="space-y-2.5">
                    {/* Top Badges */}
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${getCategoryColor(
                          doc.doc_type,
                          doc.category
                        )}`}
                      >
                        {getCategoryIcon(doc.doc_type, doc.category)}
                        {doc.category}
                      </span>

                      {doc.pages && (
                        <span className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                          <FileText className="w-3 h-3" />
                          {doc.pages} Pages
                        </span>
                      )}
                    </div>

                    {/* Document Title */}
                    <h4 className="text-sm font-bold text-foreground group-hover:text-blue-500 transition-colors leading-snug">
                      {doc.title}
                    </h4>

                    {/* Notes & Summary Description */}
                    <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
                      {doc.notes}
                    </p>

                    {/* Subject Tags */}
                    {doc.subject_tags && doc.subject_tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {doc.subject_tags.slice(0, 6).map((tag, tIdx) => (
                          <button
                            key={tIdx}
                            type="button"
                            onClick={() => onTagClick && onTagClick(tag)}
                            className="px-2 py-0.5 rounded text-[10px] font-medium bg-secondary/80 text-muted-foreground hover:bg-blue-500/20 hover:text-blue-400 transition-colors flex items-center gap-1"
                          >
                            <Tag className="w-2.5 h-2.5 text-slate-400" />
                            {tag}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Document Footer Actions — Row 1 (Audit & Source) and Row 2 (Query button bottom-right) */}
                  <div className="pt-3 border-t border-border space-y-2.5">
                    {/* Row 1: Audit Cycle and Source */}
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      {doc.review_days ? (
                        <span className="text-[11px] font-medium flex items-center gap-1">
                          <Clock className="w-3 h-3 text-emerald-500" />
                          Audit cycle: {doc.review_days}d
                        </span>
                      ) : (
                        <span />
                      )}

                      {doc.source_url && (
                        <a
                          href={doc.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-muted-foreground hover:text-foreground text-[11px] font-semibold flex items-center gap-1 px-2 py-0.5 rounded hover:bg-secondary transition-colors"
                          title="View Official Source Text"
                        >
                          <span>{doc.source_name || "Source"}</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>

                    {/* Row 2: Query Button Single Row Bottom-Right */}
                    <div className="flex items-center justify-end">
                      <Link
                        to={`/query?municipality=${jurisdiction.id}&doc=${doc.doc_id}`}
                        className="tt-btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5 shadow-sm"
                        title="Query this document with AI"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Query</span>
                      </Link>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* AHJ Department Contact Card */}
          {jurisdiction.ahj && (
            <div className="p-5 bg-secondary/30 rounded-xl border border-border/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-xs">
              <div className="space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Authority Having Jurisdiction (AHJ) Contact
                </span>
                <p className="font-bold text-foreground">{jurisdiction.ahj.name}</p>
                <p className="text-muted-foreground">
                  {jurisdiction.ahj.department} • {jurisdiction.ahj.address}
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
