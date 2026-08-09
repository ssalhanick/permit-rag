import React from "react";
import { Link } from "react-router-dom";
import { Check, Sparkles, Building2, ExternalLink, ShieldCheck, HelpCircle } from "lucide-react";
import { JURISDICTIONS } from "../../data/coverageCatalogData.js";

/**
 * CoverageComparisonMatrix
 * Side-by-side marketing matrix comparing regulatory depth and code categories
 * across all core jurisdictions.
 */
export default function CoverageComparisonMatrix({ onSelectJurisdiction }) {
  const comparisonData = [
    {
      id: "dallas",
      name: "Dallas",
      type: "Municipal",
      buildingCode: "Code Vol II (646p)",
      zoning: "Code Vol I & III",
      fireSafety: "Dallas Fire Code 2021",
      energyCode: "2021 IECC Baseline",
      checklists: "Residential 1 & 2 Family",
      fees: "2024 Official Schedule",
      aiSearch: true,
    },
    {
      id: "plano",
      name: "Plano",
      type: "Municipal",
      buildingCode: "Municode Part 2 (480p)",
      zoning: "Municode Master & Part 3",
      fireSafety: "Fire Prevention Part 2",
      energyCode: "NEC 2023 & IECC",
      checklists: "Inspections Portal Guide",
      fees: "Standard Municode",
      aiSearch: true,
    },
    {
      id: "frisco",
      name: "Frisco",
      type: "Municipal",
      buildingCode: "eCode360 Chapter 18",
      zoning: "Unified Dev Code (UDC)",
      fireSafety: "Chapter 18 Fire Safety",
      energyCode: "2024 IECC (Ord 2026-06-42)",
      checklists: "UDC Submittal Checklist",
      fees: "Development Fee Matrix",
      aiSearch: true,
    },
    {
      id: "mckinney",
      name: "McKinney",
      type: "Municipal",
      buildingCode: "Chapter 14 Building Code",
      zoning: "Municode Historic & UDC",
      fireSafety: "Chapter 14 Fire Code",
      energyCode: "2021 IECC Baseline",
      checklists: "Building Safety Submittals",
      fees: "Municipal Fee Schedule",
      aiSearch: true,
    },
    {
      id: "fortworth",
      name: "Fort Worth",
      type: "Municipal",
      buildingCode: "UpCodes Amendments",
      zoning: "American Legal (1,133p)",
      fireSafety: "UpCodes Fire Safety",
      energyCode: "2021 IECC Baseline",
      checklists: "Development Services Guide",
      fees: "City Fee Ordinance",
      aiSearch: true,
    },
    {
      id: "texas",
      name: "State of Texas",
      type: "Statewide",
      buildingCode: "TDLR State Standards",
      zoning: "Statewide Land Powers",
      fireSafety: "State Fire Marshal Rules",
      energyCode: "State Energy Plan & NEC",
      checklists: "TDLR TAS Inspection Forms",
      fees: "TDLR Registration Fees",
      aiSearch: true,
    },
    {
      id: "federal",
      name: "Federal USA",
      type: "Federal",
      buildingCode: "OSHA 29 CFR 1926",
      zoning: "Federal Land & EPA",
      fireSafety: "OSHA Life Safety",
      energyCode: "Federal Energy Standards",
      checklists: "EPA SWPPP & ADA Forms",
      fees: "Federal Filing Criteria",
      aiSearch: true,
    },
  ];

  return (
    <div className="bg-card rounded-2xl border border-border shadow-md overflow-hidden space-y-6 p-6 sm:p-8">
      <div className="space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 uppercase tracking-wider">
          <ShieldCheck className="w-3.5 h-3.5" />
          Cross-Jurisdiction Comparison
        </div>
        <h3 className="text-xl sm:text-2xl font-extrabold text-foreground tracking-tight">
          Regulatory Depth & Code Category Matrix
        </h3>
        <p className="text-sm text-muted-foreground max-w-3xl">
          Permit RAG continuously parses, vectorizes, and verifies full municipal codes, zoning bylaws, state statutes, and permit checklists so you can build with confidence anywhere in DFW.
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-border bg-secondary/40 text-muted-foreground font-bold uppercase tracking-wider text-[11px]">
              <th className="py-3.5 px-4 rounded-l-xl">Jurisdiction</th>
              <th className="py-3.5 px-3">Building Code</th>
              <th className="py-3.5 px-3">Zoning / UDC</th>
              <th className="py-3.5 px-3">Fire Safety</th>
              <th className="py-3.5 px-3">Energy (IECC / NEC)</th>
              <th className="py-3.5 px-3">Checklists</th>
              <th className="py-3.5 px-3">Fee Schedule</th>
              <th className="py-3.5 px-4 text-center rounded-r-xl">AI Grounded</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60 font-medium text-foreground">
            {comparisonData.map((item) => (
              <tr
                key={item.id}
                className="hover:bg-secondary/30 transition-colors cursor-pointer group"
                onClick={() => onSelectJurisdiction && onSelectJurisdiction(item.id)}
              >
                <td className="py-4 px-4 font-bold text-sm text-foreground flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-blue-500 group-hover:scale-110 transition-transform" />
                  <div>
                    <span className="block group-hover:text-blue-500 transition-colors">{item.name}</span>
                    <span className="text-[10px] font-normal text-muted-foreground">{item.type}</span>
                  </div>
                </td>
                <td className="py-4 px-3 text-muted-foreground">{item.buildingCode}</td>
                <td className="py-4 px-3 text-muted-foreground">{item.zoning}</td>
                <td className="py-4 px-3 text-muted-foreground">{item.fireSafety}</td>
                <td className="py-4 px-3">
                  <span className="font-semibold text-blue-600 dark:text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded">
                    {item.energyCode}
                  </span>
                </td>
                <td className="py-4 px-3 text-muted-foreground">{item.checklists}</td>
                <td className="py-4 px-3 text-muted-foreground">{item.fees}</td>
                <td className="py-4 px-4 text-center">
                  <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
