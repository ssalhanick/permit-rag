# Overlay Petitions — Internal Guide

Internal reference for staff and trusted project members on sourcing, submitting,
and reviewing historic/conservation-district and HOA overlay petitions (migration
038 — see `docs/jurisdiction_and_gis_runbook.md` Phase 4 for the technical design).

## What an overlay is

A named, geometrically-bounded area — a historic district, a conservation district,
or an HOA — narrower than a city, whose documentation (design guidelines, bylaws,
certificate-of-appropriateness rules) only applies to properties physically inside
it. An approved overlay's documents surface for **any** project whose address falls
inside that boundary, not just the project that petitioned it.

## Finding a source document

- **Historic/conservation districts**: check the city's own planning or historic
  preservation commission page first — most DFW cities publish district guidelines
  as a PDF. If the city has an open-data GIS portal (see
  `docs/backlog.md`'s DFW Cities table for known links), search it for "historic
  district" or "conservation district" layers/documents. For federal-register
  context, the National Register of Historic Places has a public GIS layer via the
  National Park Service, though it rarely covers *local* district rules — it's a
  starting point, not a substitute for the city's own designation document.
- **HOAs**: the HOA's own bylaws/CC&Rs (Covenants, Conditions & Restrictions),
  usually available from the HOA's management company or the county deed records
  office where the property is filed. A homeowner petitioning their own HOA
  typically already has a copy.

## Submitting a petition

1. The petitioning project must have an address/coordinates on file (Settings page).
2. From the project dashboard (or the "Petition this area" banner CTA), go to
   **Petition an area**, fill in the name, pick a type, attach the source document,
   and submit.
3. This creates the overlay in `petitioned` status with a coarse default boundary
   (a ~200m buffer around the project's address) and schedules the document for
   chunking/embedding in the background — same pipeline as any other upload.

## Reviewing a petition (staff)

- `GET /admin/overlays/pending` lists petitions awaiting review (oldest first).
- Confirm the source document is genuine and correctly scoped before approving —
  nothing blocks a bad-faith or mistaken petition from being submitted; review is
  the actual gate, not the submission step.
- `PATCH /admin/overlays/{overlay_id}/approve` approves it. If you have a more
  precise boundary than the default buffer (e.g. from a city GIS shapefile or by
  tracing the district on a map), pass it as `geojson_polygon` in the request body
  to replace the default buffer with the real boundary before approving.
- `POST /admin/overlays/{overlay_id}/reject` rejects a petition that shouldn't be
  approved (document doesn't support the claimed overlay, wrong location, etc.).
- Once approved, the overlay's documents are live immediately for any project
  whose address falls inside its boundary — no redeploy or re-ingest needed.
