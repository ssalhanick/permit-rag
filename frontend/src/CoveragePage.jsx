import React, { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  MapPin,
  Search,
  Building2,
  FileText,
  ShieldCheck,
  Sparkles,
  Layers,
  CheckCircle2,
  ExternalLink,
  Send,
  Compass,
  ArrowRight,
  Filter,
  Globe
} from "lucide-react";
import InteractiveCoverageMap from "./components/coverage/InteractiveCoverageMap.jsx";
import JurisdictionSpotlight from "./components/coverage/JurisdictionSpotlight.jsx";
import CoverageComparisonMatrix from "./components/coverage/CoverageComparisonMatrix.jsx";
import PetitionJurisdictionModal from "./components/coverage/PetitionJurisdictionModal.jsx";
import {
  JURISDICTIONS,
  COVERED_STATES,
  COVERED_CITIES,
  getCoverageStats,
  searchCoverage,
} from "./data/coverageCatalogData.js";

/**
 * CoveragePage
 * Standalone, marketing-focused interactive coverage map and multi-state regulatory catalog explorer.
 */
export default function CoveragePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialJurisdiction = searchParams.get("city") || searchParams.get("jurisdiction") || "dallas";

  const [selectedJurisdictionId, setSelectedJurisdictionId] = useState(initialJurisdiction);
  const [searchQuery, setSearchQuery] = useState("");
  const [authorityFilter, setAuthorityFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [showCorridors, setShowCorridors] = useState(true);
  const [isPetitionModalOpen, setIsPetitionModalOpen] = useState(false);
  const [petitionTarget, setPetitionTarget] = useState(null);

  const stats = getCoverageStats();

  // Sync url param if changed
  useEffect(() => {
    const city = searchParams.get("city") || searchParams.get("jurisdiction");
    if (city && city !== selectedJurisdictionId) {
      setSelectedJurisdictionId(city);
    }
  }, [searchParams]);

  const handleSelectJurisdiction = (id) => {
    setSelectedJurisdictionId(id);
    setSearchParams({ city: id });
  };

  const handleOpenPetition = (target = null) => {
    setPetitionTarget(target);
    setIsPetitionModalOpen(true);
  };

  const handleTagClick = (tag) => {
    setSearchQuery(tag);
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Marketing Hero Section ── */}
      <section className="relative overflow-hidden pt-10 pb-8 px-4 sm:px-6 lg:px-8 border-b border-border bg-gradient-to-b from-secondary/30 via-background to-background">
        <div className="max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-3 max-w-3xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 uppercase tracking-wider">
                <Compass className="w-3.5 h-3.5" />
                Permit RAG Multi-State GIS & Regulatory Catalog
              </div>
              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-foreground">
                Explore Municipal & Statewide Regulatory Codes
              </h1>
              <p className="text-base sm:text-lg text-muted-foreground leading-relaxed">
                Visualize verified building codes, local amendments, zoning bylaws, and permit checklists across active states with instant RAG retrieval.
              </p>
            </div>

            {/* Metric KPI Counter Badges */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 shrink-0">
              <div className="p-4 rounded-2xl bg-card border border-border text-center shadow-sm">
                <span className="block text-2xl font-black text-foreground">
                  {stats.totalJurisdictions}
                </span>
                <span className="text-xs font-semibold text-muted-foreground">
                  Covered Authorities
                </span>
              </div>
              <div className="p-4 rounded-2xl bg-card border border-border text-center shadow-sm">
                <span className="block text-2xl font-black text-blue-500">
                  {stats.totalDocuments}+
                </span>
                <span className="text-xs font-semibold text-muted-foreground">
                  Indexed Codes
                </span>
              </div>
              <div className="p-4 rounded-2xl bg-card border border-border text-center shadow-sm">
                <span className="block text-2xl font-black text-emerald-500">
                  {stats.totalPagesIndexed.toLocaleString()}+
                </span>
                <span className="text-xs font-semibold text-muted-foreground">
                  Pages Vectorized
                </span>
              </div>
              <div className="p-4 rounded-2xl bg-card border border-border text-center shadow-sm">
                <span className="block text-2xl font-black text-indigo-500">
                  100%
                </span>
                <span className="text-xs font-semibold text-muted-foreground">
                  Grounded Citations
                </span>
              </div>
            </div>
          </div>

          {/* ── Search & Filter Command Bar ── */}
          <div className="p-4 rounded-2xl bg-card border border-border shadow-md space-y-3">
            <div className="flex flex-col sm:flex-row items-center gap-3">
              {/* Text Search Input */}
              <div className="relative flex-1 w-full">
                <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Search by city, state, or code keyword (e.g., 'Dallas', 'Fishers', 'Setbacks', 'Fire Code', 'TAS')..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="tt-input w-full pl-10 pr-4 py-2.5 text-sm rounded-xl"
                />
              </div>

              {/* Clear button if active query */}
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="tt-btn-secondary text-xs px-3 py-2 shrink-0"
                >
                  Clear Search
                </button>
              )}

              {/* Request New Jurisdiction CTA Button */}
              <button
                type="button"
                onClick={() => handleOpenPetition(null)}
                className="tt-btn-primary text-xs px-4 py-2.5 shrink-0 flex items-center gap-2 shadow-md shadow-blue-500/20"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Petition a City</span>
              </button>
            </div>

            {/* Quick Authority & State Filters */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border text-xs">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-bold text-muted-foreground mr-1 flex items-center gap-1">
                  <Filter className="w-3 h-3" />
                  Filter Coverage:
                </span>
                {[
                  { id: "all", label: "All Regions" },
                  { id: "texas", label: "Texas (TX)" },
                  { id: "indiana", label: "Indiana (IN)" },
                  { id: "federal", label: "Federal Standards" },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setAuthorityFilter(item.id);
                      if (item.id === "texas") handleSelectJurisdiction("texas");
                      else if (item.id === "indiana") handleSelectJurisdiction("fishers");
                      else if (item.id === "federal") handleSelectJurisdiction("federal");
                    }}
                    className={`px-2.5 py-1 rounded-lg font-semibold transition-all ${
                      authorityFilter === item.id
                        ? "bg-blue-600 text-white shadow-sm"
                        : "bg-secondary/70 text-muted-foreground hover:text-foreground hover:bg-secondary"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              {/* Layer Toggles */}
              <div className="flex items-center gap-4 text-muted-foreground font-medium">
                <label className="flex items-center gap-1.5 cursor-pointer hover:text-foreground">
                  <input
                    type="checkbox"
                    checked={showCorridors}
                    onChange={(e) => setShowCorridors(e.target.checked)}
                    className="rounded border-border"
                  />
                  <span>Major Express Corridors</span>
                </label>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Main Interactive Map & Jurisdiction Spotlight Section ── */}
      <section className="py-8 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto space-y-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left: Vector Interactive Coverage Map (7 cols on desktop) */}
          <div className="lg:col-span-7 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                <MapPin className="w-5 h-5 text-emerald-500" />
                Interactive Jurisdiction Navigator
              </h2>
              <span className="text-xs text-muted-foreground">
                Use City, State, or Country navigation
              </span>
            </div>

            <InteractiveCoverageMap
              selectedJurisdictionId={selectedJurisdictionId}
              onSelectJurisdiction={handleSelectJurisdiction}
              showCorridors={showCorridors}
            />

            {/* Quick City Selector Bar (Clean list of covered jurisdictions, no pipeline fluff) */}
            <div className="p-4 bg-card rounded-2xl border border-border shadow-sm space-y-3">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground block">
                Quick Jump to Jurisdiction:
              </span>
              <div className="flex flex-wrap items-center gap-2">
                {JURISDICTIONS.map((j) => (
                  <button
                    key={j.id}
                    type="button"
                    onClick={() => handleSelectJurisdiction(j.id)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
                      selectedJurisdictionId === j.id
                        ? "bg-blue-600 text-white shadow-md shadow-blue-500/20 scale-105"
                        : "bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary"
                    }`}
                  >
                    <Building2 className="w-3.5 h-3.5" />
                    <span>{j.name}</span>
                    <span className="opacity-75 text-[10px]">({j.documents.length})</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right: Selected Jurisdiction Document Spotlight Drawer (5 cols on desktop, single column long scroll) */}
          <div className="lg:col-span-5 space-y-4 max-h-[880px] overflow-y-auto pr-1">
            <JurisdictionSpotlight
              jurisdictionId={selectedJurisdictionId}
              onTagClick={handleTagClick}
              onRequestPetition={handleOpenPetition}
            />
          </div>
        </div>

        {/* ── Cross-Jurisdiction Comparison Matrix Section ── */}
        <div className="pt-8">
          <CoverageComparisonMatrix onSelectJurisdiction={handleSelectJurisdiction} />
        </div>

        {/* ── Marketing Conversion Call to Action Section ── */}
        <div className="rounded-3xl bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 text-white p-8 sm:p-12 shadow-2xl space-y-6 relative overflow-hidden">
          {/* Subtle Background Glows */}
          <div className="absolute -right-10 -bottom-10 w-64 h-64 bg-white/10 rounded-full blur-3xl pointer-events-none" />

          <div className="max-w-2xl space-y-3 relative z-10">
            <span className="px-3 py-1 rounded-full text-xs font-extrabold uppercase tracking-wider bg-white/20 text-white backdrop-blur-md">
              Instant Compliance Verification
            </span>
            <h2 className="text-2xl sm:text-4xl font-black tracking-tight">
              Ready to verify permit requirements for your building project?
            </h2>
            <p className="text-sm sm:text-base text-blue-100 leading-relaxed">
              Test queries with instant grounding against official municipal codes, zoning bylaws, and checklists.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-4 relative z-10 pt-2">
            <Link
              to={`/query?municipality=${selectedJurisdictionId}`}
              className="px-6 py-3 rounded-xl bg-white text-blue-600 font-bold text-sm hover:bg-blue-50 transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5 flex items-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              <span>Ask AI About {selectedJurisdictionId.toUpperCase()} Code</span>
            </Link>

            <Link
              to="/kickoff"
              className="px-6 py-3 rounded-xl bg-blue-700/80 hover:bg-blue-700 text-white font-bold text-sm border border-white/20 transition-all flex items-center gap-2"
            >
              <span>Start Project Kickoff</span>
              <ArrowRight className="w-4 h-4" />
            </Link>

            <button
              type="button"
              onClick={() => handleOpenPetition(null)}
              className="px-4 py-3 rounded-xl bg-transparent hover:bg-white/10 text-white text-xs font-semibold transition-colors flex items-center gap-1.5"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Petition a New City</span>
            </button>
          </div>
        </div>
      </section>

      {/* ── Request / Petition Modal ── */}
      <PetitionJurisdictionModal
        isOpen={isPetitionModalOpen}
        onClose={() => setIsPetitionModalOpen(false)}
        prefilledJurisdiction={petitionTarget}
      />
    </div>
  );
}
