/**
 * contractorOptions.js — Shared vocab for contractor profile forms.
 *
 * TRADES mirrors forms/ontology.py's work.type enum (the canonical work-type
 * vocabulary used across the kickoff wizard and permit rules) so a
 * contractor's declared trades line up with how homeowner projects are tagged.
 */

export const TRADES = [
  "Plumbing",
  "Electrical",
  "HVAC / Mechanical",
  "Structural / Framing",
  "Roofing",
  "Deck / Patio Build",
  "Pool / Spa",
  "Demolition",
  "Windows / Doors",
  "Paint / Drywall",
  "Flooring",
  "Tile / Backsplash",
];

/**
 * DFW cities this app covers (AGENTS.md). ids match db/seeds/jurisdictions.sql
 * slugs where a corpus jurisdiction already exists (dallas, plano, fortworth);
 * frisco/mckinney don't have ingested documents yet but are still valid
 * service-area tags for a contractor profile.
 */
export const SERVICE_MUNICIPALITIES = [
  { id: "dallas", label: "Dallas" },
  { id: "plano", label: "Plano" },
  { id: "frisco", label: "Frisco" },
  { id: "mckinney", label: "McKinney" },
  { id: "fortworth", label: "Fort Worth" },
];
