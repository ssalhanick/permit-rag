import React, { useState } from "react";
import { Link } from "react-router-dom";
import {
  MapPin,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Building2,
  FileText,
  Layers,
  CheckCircle2,
  Compass
} from "lucide-react";
import { JURISDICTIONS, getCoverageStats } from "../../data/coverageCatalogData.js";

/**
 * CoverageMapLandingWidget
 * Interactive coverage preview designed specifically for marketing on LandingPage.jsx.
 */
export default function CoverageMapLandingWidget() {
  const [selectedId, setSelectedId] = useState("dallas");
  const stats = getCoverageStats();

  const selectedJurisdiction =
    JURISDICTIONS.find((j) => j.id === selectedId) || JURISDICTIONS[0];

  const primaryCities = JURISDICTIONS.filter((j) => j.type === "municipal" && j.state === "Texas");

  return (
    <div className="w-full bg-card rounded-3xl border border-border shadow-xl overflow-hidden p-6 sm:p-10 space-y-8">
      {/* ── Header & Metric Counters ── */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
        <div className="space-y-2 max-w-2xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 uppercase tracking-wider">
            <Compass className="w-3.5 h-3.5" />
            Interactive Jurisdiction Coverage
          </div>
          <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-foreground tracking-tight">
            Explore Verified Regulatory Codes Across North Texas
          </h2>
          <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
            Click any municipality below to preview its active building codes, zoning ordinances, checklists, and local amendments.
          </p>
        </div>

        {/* Live Metric Badges */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="px-4 py-2.5 rounded-2xl bg-secondary/70 border border-border text-center">
            <span className="block text-xl font-extrabold text-foreground">
              {stats.totalDocuments}+
            </span>
            <span className="text-[11px] font-semibold text-muted-foreground">
              Verified Codes
            </span>
          </div>
          <div className="px-4 py-2.5 rounded-2xl bg-secondary/70 border border-border text-center">
            <span className="block text-xl font-extrabold text-emerald-500">
              100%
            </span>
            <span className="text-[11px] font-semibold text-muted-foreground">
              Grounded RAG
            </span>
          </div>
          <div className="px-4 py-2.5 rounded-2xl bg-secondary/70 border border-border text-center">
            <span className="block text-xl font-extrabold text-blue-500">
              {stats.totalPagesIndexed.toLocaleString()}+
            </span>
            <span className="text-[11px] font-semibold text-muted-foreground">
              Pages Indexed
            </span>
          </div>
        </div>
      </div>

      {/* ── Interactive City Selectors ── */}
      <div className="flex flex-wrap items-center gap-2">
        {primaryCities.map((city) => {
          const isSelected = city.id === selectedId;
          return (
            <button
              key={city.id}
              type="button"
              onClick={() => setSelectedId(city.id)}
              className={`px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition-all flex items-center gap-2 ${
                isSelected
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-500/25 scale-105"
                  : "bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary"
              }`}
            >
              <Building2 className={`w-4 h-4 ${isSelected ? "text-white" : "text-blue-500"}`} />
              <span>{city.name}</span>
              <span
                className={`px-1.5 py-0.5 rounded-full text-[10px] ${
                  isSelected ? "bg-blue-800 text-blue-100" : "bg-card text-muted-foreground"
                }`}
              >
                {city.documents.length} Docs
              </span>
            </button>
          );
        })}

        {/* State & Federal Tabs */}
        {["texas", "federal"].map((id) => {
          const item = JURISDICTIONS.find((j) => j.id === id);
          if (!item) return null;
          const isSelected = item.id === selectedId;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setSelectedId(item.id)}
              className={`px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition-all flex items-center gap-2 ${
                isSelected
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/25 scale-105"
                  : "bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary"
              }`}
            >
              <ShieldCheck className={`w-4 h-4 ${isSelected ? "text-white" : "text-indigo-400"}`} />
              <span>{item.name}</span>
              <span
                className={`px-1.5 py-0.5 rounded-full text-[10px] ${
                  isSelected ? "bg-indigo-800 text-indigo-100" : "bg-card text-muted-foreground"
                }`}
              >
                {item.documents.length}
              </span>
            </button>
          );
        })}
      </div>

      {/* ── Main Interactive Split: Map Graphic + Document Spotlight ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* Left: Dynamic SVG Map Graphic (5 cols) */}
        <div className="lg:col-span-5 relative rounded-2xl bg-slate-950 border border-slate-800 p-6 flex flex-col justify-between overflow-hidden min-h-[300px]">
          {/* Subtle Map Graphic */}
          <div className="absolute inset-0 pointer-events-none opacity-40">
            <svg viewBox="0 0 400 300" className="w-full h-full">
              <path
                d="M 50 80 Q 150 40 280 30 Q 350 40 370 120 Q 380 200 310 260 Q 200 280 90 240 Z"
                fill="#1e293b"
                stroke="#334155"
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
              <path d="M 210 170 L 230 110 L 250 50" stroke="#38bdf8" strokeWidth="2.5" />
              <path d="M 90 180 L 150 185 L 210 170" stroke="#10b981" strokeWidth="2.5" />
            </svg>
          </div>

          <div className="relative z-10 space-y-1">
            <div className="flex items-center gap-2 text-emerald-400 text-xs font-bold">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span>Verified Knowledge Node</span>
            </div>
            <h3 className="text-xl font-extrabold text-white">
              {selectedJurisdiction.fullName}
            </h3>
            <p className="text-xs text-slate-400">
              {selectedJurisdiction.county} • Pop. {selectedJurisdiction.population}
            </p>
          </div>

          {/* Key highlights bullet preview */}
          <div className="relative z-10 space-y-2 my-4">
            {selectedJurisdiction.highlights.slice(0, 3).map((h, i) => (
              <div key={i} className="text-xs text-slate-300 flex items-start gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
                <span>{h}</span>
              </div>
            ))}
          </div>

          <div className="relative z-10 pt-4 border-t border-slate-800/80 flex items-center justify-between">
            <span className="text-xs text-slate-400">
              <strong className="text-white">{selectedJurisdiction.documents.length}</strong> active documents
            </span>
            <Link
              to="/coverage"
              className="text-xs font-bold text-blue-400 hover:text-blue-300 flex items-center gap-1 group"
            >
              <span>Full Interactive Map</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </div>

        {/* Right: Document List Preview (7 cols) */}
        <div className="lg:col-span-7 bg-secondary/30 rounded-2xl border border-border p-6 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-blue-500" />
                Indexed Codes & Checklists for {selectedJurisdiction.name}:
              </h4>
              <span className="text-xs font-semibold text-blue-600 dark:text-blue-400">
                {selectedJurisdiction.documents.length} Files Ready
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {selectedJurisdiction.documents.slice(0, 4).map((doc) => (
                <div
                  key={doc.doc_id}
                  className="p-3.5 bg-card rounded-xl border border-border hover:border-blue-500/40 transition-all flex flex-col justify-between space-y-2 group"
                >
                  <div>
                    <span className="inline-block px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 mb-1">
                      {doc.category}
                    </span>
                    <h5 className="text-xs font-bold text-foreground group-hover:text-blue-500 transition-colors line-clamp-1">
                      {doc.title}
                    </h5>
                    <p className="text-[11px] text-muted-foreground line-clamp-2 mt-1">
                      {doc.notes}
                    </p>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1 border-t border-border">
                    <span>{doc.pages ? `${doc.pages} Pages` : "Full Code"}</span>
                    <Link
                      to={`/query?municipality=${selectedJurisdiction.id}&doc=${doc.doc_id}`}
                      className="font-bold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-0.5"
                    >
                      <Sparkles className="w-2.5 h-2.5" />
                      <span>Ask AI</span>
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Launch Full Map Button */}
          <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              Search by address, compare zoning setback tables, and review official AHJ links in our full Coverage Hub.
            </p>
            <Link
              to="/coverage"
              className="tt-btn-primary text-xs px-5 py-2.5 shrink-0 flex items-center gap-2 shadow-lg shadow-blue-500/20"
            >
              <span>Launch Full Coverage Map</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
