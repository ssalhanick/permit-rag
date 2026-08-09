import React, { useState, useRef, useEffect } from "react";
import {
  MapPin,
  Layers,
  Sparkles,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  ShieldCheck,
  FileText,
  Building2,
  Compass,
  ChevronDown,
  ChevronRight,
  Globe,
  Navigation,
  CheckCircle2,
  Clock
} from "lucide-react";
import {
  JURISDICTIONS,
  COVERED_STATES,
  COVERED_CITIES,
} from "../../data/coverageCatalogData.js";

/**
 * InteractiveCoverageMap
 * Hierarchical SVG GIS map engine supporting Country (USA) -> State (TX, IN) -> City (Dallas, Plano, Frisco, etc.)
 * with authentic GIS polygons, regional corridors, interactive state & city nodes, and multi-level zoom HUD.
 */
export default function InteractiveCoverageMap({
  selectedJurisdictionId = "dallas",
  onSelectJurisdiction,
  showCorridors = true,
}) {
  // Navigation hierarchy: "country" | "state" | "city"
  const [navLevel, setNavLevel] = useState("city");
  const [selectedStateCode, setSelectedStateCode] = useState("TX");
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredEntity, setHoveredEntity] = useState(null);

  // Dropdown open states for HUD
  const [isCityDropdownOpen, setIsCityDropdownOpen] = useState(false);
  const [isStateDropdownOpen, setIsStateDropdownOpen] = useState(false);

  const containerRef = useRef(null);

  // Current selected jurisdiction object
  const currentJurisdiction = JURISDICTIONS.find((j) => j.id === selectedJurisdictionId) || JURISDICTIONS[0];

  // Sync state if selectedJurisdictionId changes externally
  useEffect(() => {
    if (selectedJurisdictionId === "texas") {
      setNavLevel("state");
      setSelectedStateCode("TX");
    } else if (selectedJurisdictionId === "federal") {
      setNavLevel("country");
    } else {
      const match = JURISDICTIONS.find((j) => j.id === selectedJurisdictionId);
      if (match) {
        if (match.stateCode === "TX") setSelectedStateCode("TX");
        if (match.stateCode === "IN") setSelectedStateCode("IN");
        setNavLevel("city");
      }
    }
  }, [selectedJurisdictionId]);

  // Handle Drag Panning
  const handleMouseDown = (e) => {
    // Only drag if not clicking on interactive elements
    if (e.target.closest("button") || e.target.closest(".dropdown-menu")) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
  };

  const handleMouseMove = (e) => {
    if (!isDragging) return;
    setPanOffset({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Zoom controls
  const handleZoomIn = () => setZoomLevel((prev) => Math.min(prev + 0.3, 3));
  const handleZoomOut = () => setZoomLevel((prev) => Math.max(prev - 0.3, 0.7));
  const handleResetView = () => {
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
  };

  // Level switch handlers
  const handleSelectCountryLevel = () => {
    setNavLevel("country");
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
    setIsCityDropdownOpen(false);
    setIsStateDropdownOpen(false);
    if (onSelectJurisdiction) onSelectJurisdiction("federal");
  };

  const handleSelectState = (stateCode) => {
    setSelectedStateCode(stateCode);
    setNavLevel("state");
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
    setIsCityDropdownOpen(false);
    setIsStateDropdownOpen(false);

    if (stateCode === "TX") {
      if (onSelectJurisdiction) onSelectJurisdiction("texas");
    } else if (stateCode === "IN") {
      if (onSelectJurisdiction) onSelectJurisdiction("fishers");
    }
  };

  const handleSelectCity = (cityId) => {
    setNavLevel("city");
    const city = JURISDICTIONS.find((j) => j.id === cityId);
    if (city) {
      if (city.stateCode === "TX") setSelectedStateCode("TX");
      if (city.stateCode === "IN") setSelectedStateCode("IN");
    }
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
    setIsCityDropdownOpen(false);
    setIsStateDropdownOpen(false);
    if (onSelectJurisdiction) onSelectJurisdiction(cityId);
  };

  // Compute dynamic viewBox based on nav level
  const getViewBox = () => {
    if (navLevel === "country") {
      return "0 0 960 600";
    }
    if (navLevel === "state") {
      if (selectedStateCode === "TX") {
        // Zoom on Texas region
        return "120 100 680 480";
      }
      if (selectedStateCode === "IN") {
        // Zoom on Indiana region
        return "500 80 340 320";
      }
      return "0 0 960 600";
    }
    // City level
    if (selectedStateCode === "IN" || selectedJurisdictionId === "fishers") {
      return "540 120 280 240";
    }
    // Texas City (DFW Metro focus)
    if (selectedJurisdictionId === "fortworth") {
      return "120 200 420 340";
    }
    if (selectedJurisdictionId === "plano" || selectedJurisdictionId === "frisco" || selectedJurisdictionId === "mckinney") {
      return "340 60 380 320";
    }
    // Dallas or default Texas Metro
    return "240 100 500 420";
  };

  const activeTexasCities = JURISDICTIONS.filter((j) => j.type === "municipal" && j.stateCode === "TX");
  const activeIndianaCities = JURISDICTIONS.filter((j) => j.type === "municipal" && j.stateCode === "IN");

  return (
    <div className="relative w-full rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800 bg-slate-950 text-slate-100 shadow-2xl select-none">
      {/* ── Top Map Navigation HUD & Dropdown Controls ── */}
      <div className="absolute top-3.5 left-3.5 right-3.5 z-30 flex flex-wrap items-center justify-between gap-2.5 pointer-events-none">
        {/* Left: Hierarchical Selector (City > State > Country) */}
        <div className="inline-flex items-center gap-1.5 p-1 rounded-xl bg-slate-900/95 backdrop-blur-md border border-slate-700/80 shadow-xl pointer-events-auto">
          {/* 1. City Selector with Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setIsCityDropdownOpen((prev) => !prev);
                setIsStateDropdownOpen(false);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                navLevel === "city"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-500/20"
                  : "text-slate-300 hover:text-white hover:bg-slate-800"
              }`}
            >
              <Building2 className="w-3.5 h-3.5 text-blue-400" />
              <span>City: {navLevel === "city" ? currentJurisdiction.name : "Select City"}</span>
              <ChevronDown className="w-3 h-3 ml-0.5 opacity-70" />
            </button>

            {isCityDropdownOpen && (
              <div className="absolute left-0 top-full mt-1.5 w-56 rounded-xl bg-slate-900 border border-slate-700 shadow-2xl py-1.5 z-50 text-xs dropdown-menu">
                <div className="px-3 py-1 text-[10px] font-bold uppercase text-slate-500 tracking-wider">
                  Texas Cities (5)
                </div>
                {activeTexasCities.map((city) => (
                  <button
                    key={city.id}
                    type="button"
                    onClick={() => handleSelectCity(city.id)}
                    className={`w-full text-left px-3 py-1.5 flex items-center justify-between transition-colors ${
                      selectedJurisdictionId === city.id
                        ? "bg-blue-600/30 text-blue-300 font-bold"
                        : "text-slate-300 hover:bg-slate-800 hover:text-white"
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      {city.name}, TX
                    </span>
                    <span className="text-[10px] text-slate-400">{city.documents.length} docs</span>
                  </button>
                ))}

                <div className="border-t border-slate-800 my-1" />
                <div className="px-3 py-1 text-[10px] font-bold uppercase text-slate-500 tracking-wider">
                  Indiana Cities (1)
                </div>
                {activeIndianaCities.map((city) => (
                  <button
                    key={city.id}
                    type="button"
                    onClick={() => handleSelectCity(city.id)}
                    className={`w-full text-left px-3 py-1.5 flex items-center justify-between transition-colors ${
                      selectedJurisdictionId === city.id
                        ? "bg-blue-600/30 text-blue-300 font-bold"
                        : "text-slate-300 hover:bg-slate-800 hover:text-white"
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      {city.name}, IN
                    </span>
                    <span className="text-[10px] text-slate-400">{city.documents.length} docs</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Separator icon */}
          <ChevronRight className="w-3.5 h-3.5 text-slate-600" />

          {/* 2. State Selector with Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setIsStateDropdownOpen((prev) => !prev);
                setIsCityDropdownOpen(false);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                navLevel === "state"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                  : "text-slate-300 hover:text-white hover:bg-slate-800"
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
              <span>State: {selectedStateCode === "TX" ? "Texas (TX)" : "Indiana (IN)"}</span>
              <ChevronDown className="w-3 h-3 ml-0.5 opacity-70" />
            </button>

            {isStateDropdownOpen && (
              <div className="absolute left-0 top-full mt-1.5 w-52 rounded-xl bg-slate-900 border border-slate-700 shadow-2xl py-1.5 z-50 text-xs dropdown-menu">
                {COVERED_STATES.map((state) => (
                  <button
                    key={state.code}
                    type="button"
                    onClick={() => handleSelectState(state.code)}
                    className={`w-full text-left px-3 py-2 flex items-center justify-between transition-colors ${
                      selectedStateCode === state.code && navLevel === "state"
                        ? "bg-indigo-600/30 text-indigo-300 font-bold"
                        : "text-slate-300 hover:bg-slate-800 hover:text-white"
                    }`}
                  >
                    <div>
                      <div className="font-bold">{state.name} ({state.code})</div>
                      <div className="text-[10px] text-slate-400">{state.citiesCount} Cities • {state.documentsCount} Codes</div>
                    </div>
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Separator icon */}
          <ChevronRight className="w-3.5 h-3.5 text-slate-600" />

          {/* 3. Country (USA) Button */}
          <button
            type="button"
            onClick={handleSelectCountryLevel}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
              navLevel === "country"
                ? "bg-cyan-600 text-white shadow-md shadow-cyan-500/20"
                : "text-slate-300 hover:text-white hover:bg-slate-800"
            }`}
          >
            <Globe className="w-3.5 h-3.5 text-cyan-400" />
            <span>Country (USA)</span>
          </button>
        </div>

        {/* Right: Quick Zoom, Reset, & Current Breadcrumb Badge */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-900/95 backdrop-blur-md border border-slate-700/80 shadow-xl pointer-events-auto">
          <button
            type="button"
            onClick={handleZoomIn}
            className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
            title="Zoom In"
            aria-label="Zoom in"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={handleZoomOut}
            className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
            title="Zoom Out"
            aria-label="Zoom out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={handleResetView}
            className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
            title="Reset Map View"
            aria-label="Reset view"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ── Main Interactive Map Canvas (SVG Vector Engine) ── */}
      <div
        ref={containerRef}
        className="w-full h-[500px] sm:h-[560px] md:h-[620px] cursor-grab active:cursor-grabbing relative overflow-hidden"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={() => {
          setIsCityDropdownOpen(false);
          setIsStateDropdownOpen(false);
        }}
      >
        <svg
          viewBox={getViewBox()}
          className="w-full h-full object-cover transition-all duration-500 ease-out"
          style={{
            transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
            transformOrigin: "center center",
          }}
        >
          <defs>
            {/* Gradients */}
            <radialGradient id="usaMapGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#1d4ed8" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#030712" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="texasZoneGlow" cx="470" cy="300" r="220" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#030712" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="indianaZoneGlow" cx="620" cy="230" r="140" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#030712" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="activeCityPinGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#10b981" />
              <stop offset="100%" stopColor="#047857" />
            </linearGradient>
            <linearGradient id="selectedCityPinGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#38bdf8" />
              <stop offset="100%" stopColor="#1d4ed8" />
            </linearGradient>

            {/* Glowing Drop Shadows */}
            <filter id="svgGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <filter id="mapShadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#000000" floodOpacity="0.7" />
            </filter>
          </defs>

          {/* Background Grid and Radial Glow */}
          <rect x="-100" y="-100" width="1160" height="800" fill="#030712" />
          <circle cx="480" cy="300" r="420" fill="url(#usaMapGlow)" />

          {/* Subtle GIS Cartesian Grid Overlay */}
          <g stroke="#1e293b" strokeWidth="0.5" strokeDasharray="4 8" opacity="0.45">
            <line x1="0" y1="100" x2="960" y2="100" />
            <line x1="0" y1="200" x2="960" y2="200" />
            <line x1="0" y1="300" x2="960" y2="300" />
            <line x1="0" y1="400" x2="960" y2="400" />
            <line x1="0" y1="500" x2="960" y2="500" />
            <line x1="160" y1="0" x2="160" y2="600" />
            <line x1="320" y1="0" x2="320" y2="600" />
            <line x1="480" y1="0" x2="480" y2="600" />
            <line x1="640" y1="0" x2="640" y2="600" />
            <line x1="800" y1="0" x2="800" y2="600" />
          </g>

          {/* ═══════════════════════════════════════════════════════════════════
              USA CONTINENTAL VECTOR BASE MAP
              ═══════════════════════════════════════════════════════════════════ */}
          <g id="usa-states-basemap">
            {/* Generic US Boundary Backdrop */}
            {/* West Coast & Northwest */}
            <path
              d="M 120 70 L 160 65 L 170 140 L 140 180 L 150 250 L 110 320 L 130 400 L 200 450 L 210 400 L 270 390 L 320 400 L 380 440 L 380 340 L 320 340 L 320 200 L 220 200 L 220 70 Z"
              fill="#0f172a"
              stroke="#1e293b"
              strokeWidth="1.2"
            />
            {/* Northern Plains & Midwest (Excluding Indiana) */}
            <path
              d="M 320 70 L 590 70 L 590 190 L 550 260 L 520 260 L 520 340 L 380 340 L 320 340 L 320 200 L 320 70 Z"
              fill="#0f172a"
              stroke="#1e293b"
              strokeWidth="1.2"
            />
            {/* Great Lakes & Northeast */}
            <path
              d="M 590 70 L 890 90 L 910 160 L 850 220 L 780 240 L 730 220 L 680 180 L 660 190 L 660 70 Z"
              fill="#0f172a"
              stroke="#1e293b"
              strokeWidth="1.2"
            />
            {/* Southeast & Florida */}
            <path
              d="M 580 340 L 660 340 L 730 310 L 810 330 L 830 420 L 790 520 L 760 520 L 740 430 L 650 430 L 580 430 L 580 340 Z"
              fill="#0f172a"
              stroke="#1e293b"
              strokeWidth="1.2"
            />

            {/* ── INDIANA STATE POLYGON (Active State Coverage) ── */}
            <g
              id="state-indiana"
              className="cursor-pointer group"
              onClick={() => handleSelectState("IN")}
              onMouseEnter={() => setHoveredEntity({ name: "Indiana", code: "IN", type: "state", cities: 1, docs: 3 })}
              onMouseLeave={() => setHoveredEntity(null)}
            >
              <circle cx="620" cy="225" r="50" fill="url(#indianaZoneGlow)" />
              <path
                d="M 595 180 L 640 180 L 645 270 L 610 275 L 595 240 Z"
                fill={selectedStateCode === "IN" ? "#064e3b" : "#022c22"}
                stroke={selectedStateCode === "IN" ? "#10b981" : "#059669"}
                strokeWidth={selectedStateCode === "IN" ? "2.5" : "1.5"}
                className="transition-all group-hover:fill-emerald-900/80"
              />
              <text x="618" y="215" fill="#a7f3d0" fontSize="10" fontWeight="bold" textAnchor="middle">
                IN
              </text>
            </g>

            {/* ── TEXAS STATE POLYGON (Active State Coverage) ── */}
            <g
              id="state-texas"
              className="cursor-pointer group"
              onClick={() => handleSelectState("TX")}
              onMouseEnter={() => setHoveredEntity({ name: "Texas", code: "TX", type: "state", cities: 5, docs: 24 })}
              onMouseLeave={() => setHoveredEntity(null)}
            >
              <circle cx="470" cy="380" r="140" fill="url(#texasZoneGlow)" />
              {/* Detailed Geographic Texas Polygon */}
              <path
                d="M 380 340 L 480 340 L 480 365 L 560 365 L 570 420 L 530 480 L 480 540 L 440 500 L 410 490 L 350 420 L 350 380 L 380 380 Z"
                fill={selectedStateCode === "TX" ? "#1e1b4b" : "#0f172a"}
                stroke={selectedStateCode === "TX" ? "#6366f1" : "#4f46e5"}
                strokeWidth={selectedStateCode === "TX" ? "2.5" : "1.8"}
                className="transition-all group-hover:fill-indigo-950/80"
              />
              <text x="430" y="440" fill="#a5b4fc" fontSize="14" fontWeight="bold" textAnchor="middle" opacity="0.6">
                TEXAS
              </text>
            </g>
          </g>

          {/* ═══════════════════════════════════════════════════════════════════
              REGIONAL GIS ZONES & CORRIDORS (When State/City Level Active)
              ═══════════════════════════════════════════════════════════════════ */}
          {selectedStateCode === "TX" && (
            <g id="texas-gis-detail-layer">
              {/* North Texas DFW Metropolitan GIS Zone Boundary */}
              <path
                d="M 390 280 Q 470 240 570 260 Q 600 360 550 440 Q 440 460 380 420 Q 350 330 390 280 Z"
                fill="#1e293b"
                fillOpacity="0.5"
                stroke="#38bdf8"
                strokeWidth="1.2"
                strokeDasharray="4 4"
              />

              {/* Collin County Zone */}
              <path
                d="M 440 100 L 580 90 L 600 240 L 430 230 Z"
                fill="#1e1b4b"
                fillOpacity="0.4"
                stroke="#6366f1"
                strokeWidth="1"
                strokeOpacity="0.5"
              />
              <text x="510" y="115" fill="#818cf8" fontSize="9" fontWeight="bold" letterSpacing="1">
                COLLIN COUNTY
              </text>

              {/* Dallas County Zone */}
              <path
                d="M 400 250 L 570 250 L 560 410 L 390 390 Z"
                fill="#0c4a6e"
                fillOpacity="0.35"
                stroke="#0284c7"
                strokeWidth="1"
                strokeOpacity="0.5"
              />
              <text x="480" y="395" fill="#38bdf8" fontSize="9" fontWeight="bold" letterSpacing="1">
                DALLAS COUNTY
              </text>

              {/* Tarrant County Zone */}
              <path
                d="M 150 250 L 370 250 L 360 420 L 150 400 Z"
                fill="#064e3b"
                fillOpacity="0.3"
                stroke="#059669"
                strokeWidth="1"
                strokeOpacity="0.4"
              />
              <text x="220" y="405" fill="#34d399" fontSize="9" fontWeight="bold" letterSpacing="1">
                TARRANT COUNTY
              </text>

              {/* Major Corridors & Arterial Expressways */}
              {showCorridors && (
                <g strokeLinecap="round">
                  {/* Dallas North Tollway (DNT) */}
                  <path d="M 470 340 L 465 220 L 460 140" stroke="#38bdf8" strokeWidth="3" filter="url(#svgGlow)" />
                  <path d="M 470 340 L 465 220 L 460 140" stroke="#ffffff" strokeWidth="1" />

                  {/* US-75 Corridor */}
                  <path d="M 470 340 L 510 220 L 550 110" stroke="#818cf8" strokeWidth="3" />
                  <path d="M 470 340 L 510 220 L 550 110" stroke="#ffffff" strokeWidth="1" strokeDasharray="4 3" />

                  {/* SH-121 Sam Rayburn Corridor */}
                  <path d="M 200 360 L 330 280 L 460 140 L 550 110" stroke="#34d399" strokeWidth="2.5" />

                  {/* I-30 (Fort Worth to Dallas) */}
                  <path d="M 200 360 L 330 360 L 470 340" stroke="#f59e0b" strokeWidth="2.5" />

                  {/* Highway Labels */}
                  <g fontSize="8" fontWeight="bold" fill="#94a3b8">
                    <text x="445" y="235">DNT</text>
                    <text x="520" y="170">US-75</text>
                    <text x="360" y="200">SH-121</text>
                    <text x="310" y="375">I-30</text>
                  </g>
                </g>
              )}
            </g>
          )}

          {/* Indiana GIS Zone Detail (When Indiana Selected) */}
          {selectedStateCode === "IN" && (
            <g id="indiana-gis-detail-layer">
              {/* Hamilton County / Indianapolis Metro Zone Boundary */}
              <circle cx="620" cy="225" r="70" fill="#064e3b" fillOpacity="0.4" stroke="#10b981" strokeWidth="1.5" strokeDasharray="4 4" />
              <text x="620" y="175" fill="#34d399" fontSize="10" fontWeight="bold" textAnchor="middle" letterSpacing="1">
                HAMILTON COUNTY ZONE
              </text>
              {/* I-69 Corridor */}
              <path d="M 590 260 L 620 220 L 660 180" stroke="#38bdf8" strokeWidth="3" filter="url(#svgGlow)" />
              <path d="M 590 260 L 620 220 L 660 180" stroke="#ffffff" strokeWidth="1" strokeDasharray="3 3" />
              <text x="640" y="200" fill="#94a3b8" fontSize="8" fontWeight="bold">I-69</text>
            </g>
          )}

          {/* ═══════════════════════════════════════════════════════════════════
              CITY COVERAGE NODES & RADAR PINS
              ═══════════════════════════════════════════════════════════════════ */}
          {/* Texas City Pins */}
          {activeTexasCities.map((city) => {
            const isSelected = selectedJurisdictionId === city.id;
            const x = city.coordinates.mapX;
            const y = city.coordinates.mapY;
            const docCount = city.documents.length;

            return (
              <g
                key={city.id}
                className="cursor-pointer group"
                onClick={() => handleSelectCity(city.id)}
                onMouseEnter={() => setHoveredEntity({ ...city, type: "city" })}
                onMouseLeave={() => setHoveredEntity(null)}
              >
                {/* Radar Ping Wave */}
                <circle
                  cx={x}
                  cy={y}
                  r="26"
                  fill="none"
                  stroke={isSelected ? "#38bdf8" : "#10b981"}
                  strokeWidth="1.5"
                  opacity="0.4"
                  className="animate-ping origin-center"
                  style={{ transformOrigin: `${x}px ${y}px`, animationDuration: "3s" }}
                />

                {/* Outer Pin Disc */}
                <circle
                  cx={x}
                  cy={y}
                  r={isSelected ? 24 : 18}
                  fill={isSelected ? "url(#selectedCityPinGrad)" : "url(#activeCityPinGrad)"}
                  filter="url(#mapShadow)"
                  className="transition-all duration-200 group-hover:scale-110"
                  style={{ transformOrigin: `${x}px ${y}px` }}
                />

                {/* Document Counter */}
                <circle cx={x} cy={y} r={isSelected ? 13 : 9} fill="#ffffff" />
                <text
                  x={x}
                  y={y + (isSelected ? 4 : 3)}
                  textAnchor="middle"
                  fill={isSelected ? "#1e40af" : "#047857"}
                  fontSize={isSelected ? "11" : "9"}
                  fontWeight="900"
                >
                  {docCount}
                </text>

                {/* City Name Badge */}
                <g transform={`translate(${x}, ${y + (isSelected ? 30 : 26)})`}>
                  <rect
                    x="-42"
                    y="-11"
                    width="84"
                    height="22"
                    rx="11"
                    fill={isSelected ? "#1e40af" : "#0f172a"}
                    stroke={isSelected ? "#60a5fa" : "#334155"}
                    strokeWidth={isSelected ? 1.5 : 1}
                    filter="url(#mapShadow)"
                  />
                  <text
                    x="0"
                    y="4"
                    textAnchor="middle"
                    fill={isSelected ? "#ffffff" : "#f1f5f9"}
                    fontSize="10"
                    fontWeight="800"
                  >
                    {city.name}
                  </text>
                </g>
              </g>
            );
          })}

          {/* Indiana City Pin (Fishers, IN) */}
          {activeIndianaCities.map((city) => {
            const isSelected = selectedJurisdictionId === city.id;
            const x = 620;
            const y = 220;
            const docCount = city.documents.length;

            return (
              <g
                key={city.id}
                className="cursor-pointer group"
                onClick={() => handleSelectCity(city.id)}
                onMouseEnter={() => setHoveredEntity({ ...city, type: "city" })}
                onMouseLeave={() => setHoveredEntity(null)}
              >
                {/* Radar Ping Wave */}
                <circle
                  cx={x}
                  cy={y}
                  r="24"
                  fill="none"
                  stroke={isSelected ? "#38bdf8" : "#10b981"}
                  strokeWidth="1.5"
                  opacity="0.4"
                  className="animate-ping origin-center"
                  style={{ transformOrigin: `${x}px ${y}px`, animationDuration: "3s" }}
                />

                {/* Outer Pin */}
                <circle
                  cx={x}
                  cy={y}
                  r={isSelected ? 22 : 16}
                  fill={isSelected ? "url(#selectedCityPinGrad)" : "url(#activeCityPinGrad)"}
                  filter="url(#mapShadow)"
                  className="transition-all duration-200 group-hover:scale-110"
                  style={{ transformOrigin: `${x}px ${y}px` }}
                />

                <circle cx={x} cy={y} r={isSelected ? 12 : 8} fill="#ffffff" />
                <text
                  x={x}
                  y={y + (isSelected ? 4 : 3)}
                  textAnchor="middle"
                  fill={isSelected ? "#1e40af" : "#047857"}
                  fontSize={isSelected ? "10" : "8"}
                  fontWeight="900"
                >
                  {docCount}
                </text>

                {/* Badge */}
                <g transform={`translate(${x}, ${y + (isSelected ? 28 : 24)})`}>
                  <rect
                    x="-40"
                    y="-10"
                    width="80"
                    height="20"
                    rx="10"
                    fill={isSelected ? "#1e40af" : "#0f172a"}
                    stroke={isSelected ? "#60a5fa" : "#334155"}
                    strokeWidth={isSelected ? 1.5 : 1}
                    filter="url(#mapShadow)"
                  />
                  <text
                    x="0"
                    y="4"
                    textAnchor="middle"
                    fill={isSelected ? "#ffffff" : "#f1f5f9"}
                    fontSize="9"
                    fontWeight="800"
                  >
                    Fishers, IN
                  </text>
                </g>
              </g>
            );
          })}
        </svg>

        {/* ── Interactive Hover Tooltip ── */}
        {hoveredEntity && (
          <div
            className="absolute z-30 pointer-events-none p-3 bg-slate-900/95 border border-slate-700/90 rounded-xl shadow-2xl backdrop-blur-md max-w-xs text-xs"
            style={{
              left: `${Math.min(Math.max((hoveredEntity.coordinates?.mapX || 450) - 50, 20), 550)}px`,
              top: `${Math.max((hoveredEntity.coordinates?.mapY || 200) - 90, 20)}px`,
            }}
          >
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="font-extrabold text-sm text-white flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-emerald-400" />
                {hoveredEntity.fullName || hoveredEntity.name}
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                Active Coverage
              </span>
            </div>

            <p className="text-slate-300 text-[11px] mb-1.5">
              {hoveredEntity.county ? hoveredEntity.county : `${hoveredEntity.name} Coverage Area`}
              {hoveredEntity.population && ` • Pop. ${hoveredEntity.population}`}
            </p>

            {hoveredEntity.documents && (
              <div className="flex items-center gap-1.5 text-slate-400 border-t border-slate-800 pt-1.5 text-[11px]">
                <FileText className="w-3.5 h-3.5 text-blue-400" />
                <span>
                  <strong className="text-slate-100">{hoveredEntity.documents.length}</strong> indexed regulatory codes
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Bottom Map HUD Bar & Legend ── */}
      <div className="p-3.5 bg-slate-900/95 border-t border-slate-800/90 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 text-xs">
        {/* Legend */}
        <div className="flex flex-wrap items-center gap-3.5 text-slate-400">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Legend:</span>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-emerald-500/20" />
            <span className="text-slate-300 font-medium">Active Coverage Zone</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 ring-2 ring-blue-500/20" />
            <span className="text-slate-300 font-medium">Selected Municipality</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3.5 h-0.5 bg-gradient-to-r from-sky-400 to-indigo-400 rounded-full" />
            <span className="text-slate-300 font-medium">Corridor Overlay</span>
          </div>
        </div>

        {/* Selected City Quick Info Readout */}
        {currentJurisdiction && (
          <div className="flex items-center gap-2 text-left sm:text-right">
            <div>
              <div className="font-extrabold text-white flex items-center sm:justify-end gap-1.5">
                <span>{currentJurisdiction.fullName || currentJurisdiction.name}</span>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              </div>
              <span className="text-[11px] text-slate-400">
                {currentJurisdiction.documents
                  ? `${currentJurisdiction.documents.length} verified regulatory documents`
                  : "Active coverage node"}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
