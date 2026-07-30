import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, MapPin, Plus, Trash2 } from "lucide-react";
import { fetchContractorLicenses, fetchMarketplaceProjectDetail, submitBid } from "../../api.js";
import BidCard from "../../bids/BidCard.jsx";

const UNIT_OPTIONS = ["each", "sq_ft", "linear_ft", "hour"];

const inputClass =
  "w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50";
const labelClass = "block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5";

const EMPTY_LINE_ITEM = { description: "", quantity: "1", unit: "each", unit_price: "", labor_amount: "", material_amount: "", labor_hours: "" };
const EMPTY_MILESTONE = { milestone: "Deposit", percent: "" };

function lineItemTotal(item) {
  const qty = Number(item.quantity) || 0;
  const price = Number(item.unit_price) || 0;
  return qty * price;
}

export default function MarketplaceListingDetailPage() {
  const { projectId } = useParams();

  const [listing, setListing] = useState(null);
  const [licenses, setLicenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submittedBid, setSubmittedBid] = useState(null);

  const [licenseId, setLicenseId] = useState("");
  const [lineItems, setLineItems] = useState([{ ...EMPTY_LINE_ITEM }]);
  const [allowances, setAllowances] = useState([]);
  const [exclusions, setExclusions] = useState([]);
  const [paymentSchedule, setPaymentSchedule] = useState([{ ...EMPTY_MILESTONE }]);
  const [permitResponsibility, setPermitResponsibility] = useState("");
  const [timelineStart, setTimelineStart] = useState("");
  const [timelineEnd, setTimelineEnd] = useState("");
  const [timelineNotes, setTimelineNotes] = useState("");
  const [warrantyText, setWarrantyText] = useState("");
  const [warrantyYears, setWarrantyYears] = useState("");
  const [changeOrderTerms, setChangeOrderTerms] = useState("");
  const [lienWaiverIncluded, setLienWaiverIncluded] = useState(false);
  const [materialsSource, setMaterialsSource] = useState("unspecified");
  const [materialsSourceNotes, setMaterialsSourceNotes] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([fetchMarketplaceProjectDetail(projectId), fetchContractorLicenses()])
      .then(([listingRes, licensesRes]) => {
        if (!active) return;
        setListing(listingRes.data);
        const validLicenses = (licensesRes.data || []).filter(
          (l) => new Date(`${l.expiration_date}T00:00:00`) >= new Date(),
        );
        setLicenses(validLicenses);
        if (validLicenses.length > 0) {
          setLicenseId(validLicenses[0].id);
        }
      })
      .catch((err) => {
        if (active) setError(err.message || "Failed to load this listing.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  const total = useMemo(() => lineItems.reduce((sum, item) => sum + lineItemTotal(item), 0), [lineItems]);

  const updateLineItem = (idx, field) => (e) => {
    const value = e.target.value;
    setLineItems((items) => items.map((item, i) => (i === idx ? { ...item, [field]: value } : item)));
  };
  const addLineItem = () => setLineItems((items) => [...items, { ...EMPTY_LINE_ITEM }]);
  const removeLineItem = (idx) => setLineItems((items) => items.filter((_, i) => i !== idx));

  const addAllowance = () => setAllowances((rows) => [...rows, { description: "", amount: "" }]);
  const updateAllowance = (idx, field) => (e) =>
    setAllowances((rows) => rows.map((r, i) => (i === idx ? { ...r, [field]: e.target.value } : r)));
  const removeAllowance = (idx) => setAllowances((rows) => rows.filter((_, i) => i !== idx));

  const addExclusion = () => setExclusions((rows) => [...rows, { description: "" }]);
  const updateExclusion = (idx) => (e) =>
    setExclusions((rows) => rows.map((r, i) => (i === idx ? { description: e.target.value } : r)));
  const removeExclusion = (idx) => setExclusions((rows) => rows.filter((_, i) => i !== idx));

  const addMilestone = () => setPaymentSchedule((rows) => [...rows, { ...EMPTY_MILESTONE, milestone: "" }]);
  const updateMilestone = (idx, field) => (e) =>
    setPaymentSchedule((rows) => rows.map((r, i) => (i === idx ? { ...r, [field]: e.target.value } : r)));
  const removeMilestone = (idx) => setPaymentSchedule((rows) => rows.filter((_, i) => i !== idx));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!licenseId) {
      setError("Select a current license to back this bid.");
      return;
    }
    const cleanedItems = lineItems.filter((item) => item.description.trim() && item.quantity && item.unit_price);
    if (cleanedItems.length === 0) {
      setError("Add at least one priced line item.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await submitBid(projectId, {
        license_id: licenseId,
        line_items: cleanedItems.map((item) => ({
          description: item.description.trim(),
          quantity: Number(item.quantity),
          unit: item.unit,
          unit_price: Number(item.unit_price),
          labor_amount: Number(item.labor_amount) || 0,
          material_amount: Number(item.material_amount) || 0,
          labor_hours: item.labor_hours ? Number(item.labor_hours) : null,
        })),
        allowances: allowances.filter((a) => a.description.trim()).map((a) => ({ description: a.description.trim(), amount: Number(a.amount) || 0 })),
        exclusions: exclusions.filter((x) => x.description.trim()),
        payment_schedule: paymentSchedule
          .filter((m) => m.milestone.trim() && m.percent)
          .map((m) => ({ milestone: m.milestone.trim(), percent: Number(m.percent) })),
        permit_responsibility: permitResponsibility || null,
        timeline_start: timelineStart || null,
        timeline_end: timelineEnd || null,
        timeline_notes: timelineNotes || null,
        warranty_text: warrantyText || null,
        warranty_years: warrantyYears ? Number(warrantyYears) : null,
        change_order_terms: changeOrderTerms || null,
        lien_waiver_included: lienWaiverIncluded,
        materials_source: materialsSource,
        materials_source_connector: materialsSource === "contractor_supplied_connector" ? "home_depot" : null,
        materials_source_notes: materialsSourceNotes || null,
        notes: notes || null,
      });
      setSubmittedBid(res.data);
    } catch (err) {
      setError(err.message || "Failed to submit bid.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-4 sm:p-6">
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading listing…</p>
      </div>
    );
  }

  if (!listing) {
    return (
      <div className="max-w-4xl mx-auto p-4 sm:p-6">
        <div className="p-4 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-sm">
          {error || "Listing not found."}
        </div>
      </div>
    );
  }

  const { project, room_scan_summary: roomScanSummary, materials_estimate: materialsEstimate } = listing;

  if (submittedBid) {
    return (
      <div className="max-w-3xl mx-auto p-4 sm:p-6 space-y-4">
        <div className="p-4 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 rounded-xl text-sm font-semibold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>Bid submitted on {project.name}.</span>
        </div>
        <BidCard bid={submittedBid} showEvaluation />
        <Link to="/contractor/dashboard" className="tt-btn-secondary text-xs px-4 py-2.5 rounded-xl inline-block">
          Back to Open Projects
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">{project.name}</h1>
        <div className="text-xs text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-1">
          <MapPin className="w-3.5 h-3.5" />
          {project.address || project.municipality || "Location not set"}
        </div>
        {project.description && <p className="text-sm text-slate-600 dark:text-slate-300 mt-2">{project.description}</p>}
        <div className="flex flex-wrap gap-1.5 mt-3">
          {(project.work_types || []).map((wt) => (
            <span
              key={wt}
              className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold border bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300 border-slate-300 dark:border-slate-700"
            >
              {wt}
            </span>
          ))}
        </div>
      </div>

      {(roomScanSummary || materialsEstimate) && (
        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 sm:p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
            Room Scan &amp; Materials Context
          </div>
          {roomScanSummary && (
            <div className="text-sm text-slate-700 dark:text-slate-300 grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
              {roomScanSummary.floor_area_sqm != null && <div>Floor: {roomScanSummary.floor_area_sqm.toFixed(1)} m²</div>}
              {roomScanSummary.wall_area_sqm != null && <div>Walls: {roomScanSummary.wall_area_sqm.toFixed(1)} m²</div>}
              {roomScanSummary.max_ceiling_height_m != null && <div>Ceiling: {roomScanSummary.max_ceiling_height_m.toFixed(1)} m</div>}
              {roomScanSummary.wall_count != null && <div>Walls: {roomScanSummary.wall_count}</div>}
            </div>
          )}
          {materialsEstimate?.lines?.length > 0 && (
            <div className="text-xs text-slate-500 dark:text-slate-400">
              Platform materials estimate: ${materialsEstimate.total_low?.toLocaleString()}–$
              {materialsEstimate.total_high?.toLocaleString()} ({materialsEstimate.disclaimer})
            </div>
          )}
        </div>
      )}

      {licenses.length === 0 && (
        <div className="p-4 bg-amber-50 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 rounded-xl text-sm">
          You need a current, non-expired license on file before you can bid. Add one on your{" "}
          <a href="/contractor/licenses" className="underline font-semibold">
            Licenses page
          </a>
          .
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-5">
          <div>
            <label className={labelClass}>Backing License</label>
            <select value={licenseId} onChange={(e) => setLicenseId(e.target.value)} disabled={submitting} className={inputClass}>
              {licenses.length === 0 && <option value="">No valid license</option>}
              {licenses.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.trade} — #{l.license_number}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelClass}>Line Items</label>
            <div className="space-y-2">
              {lineItems.map((item, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                  <input
                    type="text"
                    placeholder="Description"
                    value={item.description}
                    onChange={updateLineItem(idx, "description")}
                    disabled={submitting}
                    className={`${inputClass} col-span-4`}
                  />
                  <input
                    type="number"
                    placeholder="Qty"
                    min="0"
                    value={item.quantity}
                    onChange={updateLineItem(idx, "quantity")}
                    disabled={submitting}
                    className={`${inputClass} col-span-1`}
                  />
                  <select value={item.unit} onChange={updateLineItem(idx, "unit")} disabled={submitting} className={`${inputClass} col-span-2`}>
                    {UNIT_OPTIONS.map((u) => (
                      <option key={u} value={u}>
                        {u}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    placeholder="Unit $"
                    min="0"
                    value={item.unit_price}
                    onChange={updateLineItem(idx, "unit_price")}
                    disabled={submitting}
                    className={`${inputClass} col-span-2`}
                  />
                  <input
                    type="number"
                    placeholder="Labor $"
                    min="0"
                    value={item.labor_amount}
                    onChange={updateLineItem(idx, "labor_amount")}
                    disabled={submitting}
                    className={`${inputClass} col-span-1`}
                  />
                  <input
                    type="number"
                    placeholder="Labor hrs"
                    min="0"
                    value={item.labor_hours}
                    onChange={updateLineItem(idx, "labor_hours")}
                    disabled={submitting}
                    className={`${inputClass} col-span-1`}
                  />
                  <button
                    type="button"
                    onClick={() => removeLineItem(idx)}
                    disabled={submitting || lineItems.length === 1}
                    className="col-span-1 text-red-600 dark:text-red-400 disabled:opacity-30"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
            <button type="button" onClick={addLineItem} disabled={submitting} className="tt-btn-secondary text-xs px-3 py-1.5 rounded-xl mt-2 flex items-center gap-1">
              <Plus className="w-3.5 h-3.5" /> Add Line Item
            </button>
            <div className="text-right text-sm font-bold text-slate-900 dark:text-slate-100 mt-2">
              Total: ${total.toLocaleString()}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label className={labelClass}>Timeline Start</label>
              <input type="date" value={timelineStart} onChange={(e) => setTimelineStart(e.target.value)} disabled={submitting} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Timeline End</label>
              <input type="date" value={timelineEnd} onChange={(e) => setTimelineEnd(e.target.value)} disabled={submitting} className={inputClass} />
            </div>
          </div>
          <div>
            <label className={labelClass}>Timeline Notes</label>
            <input type="text" value={timelineNotes} onChange={(e) => setTimelineNotes(e.target.value)} disabled={submitting} className={inputClass} />
          </div>

          <div>
            <label className={labelClass}>Who Pulls the Permit?</label>
            <select value={permitResponsibility} onChange={(e) => setPermitResponsibility(e.target.value)} disabled={submitting} className={inputClass}>
              <option value="">Not specified</option>
              <option value="contractor">Contractor</option>
              <option value="homeowner">Homeowner</option>
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label className={labelClass}>Warranty</label>
              <input
                type="text"
                placeholder="e.g. 5-year workmanship warranty"
                value={warrantyText}
                onChange={(e) => setWarrantyText(e.target.value)}
                disabled={submitting}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Warranty Years</label>
              <input type="number" min="0" value={warrantyYears} onChange={(e) => setWarrantyYears(e.target.value)} disabled={submitting} className={inputClass} />
            </div>
          </div>

          <div>
            <label className={labelClass}>Change-Order Terms</label>
            <textarea
              value={changeOrderTerms}
              onChange={(e) => setChangeOrderTerms(e.target.value)}
              disabled={submitting}
              rows={2}
              placeholder="e.g. All change orders must be submitted in writing and signed before work proceeds."
              className={inputClass}
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" checked={lienWaiverIncluded} onChange={(e) => setLienWaiverIncluded(e.target.checked)} disabled={submitting} />
            Bid includes lien-waiver language
          </label>

          <div>
            <label className={labelClass}>Materials Sourcing</label>
            <select value={materialsSource} onChange={(e) => setMaterialsSource(e.target.value)} disabled={submitting} className={inputClass}>
              <option value="unspecified">Not specified</option>
              <option value="homeowner_supplied">Homeowner sources materials (labor-only bid)</option>
              <option value="contractor_supplied_connector">I'll supply materials — Home Depot</option>
              <option value="contractor_supplied_manual">I'll supply materials — another store</option>
            </select>
            {(materialsSource === "contractor_supplied_manual" || materialsSource === "contractor_supplied_connector") && (
              <input
                type="text"
                placeholder="Store name / notes on where materials will be sourced"
                value={materialsSourceNotes}
                onChange={(e) => setMaterialsSourceNotes(e.target.value)}
                disabled={submitting}
                className={`${inputClass} mt-2`}
              />
            )}
          </div>

          <div>
            <label className={labelClass}>Allowances</label>
            {allowances.map((a, idx) => (
              <div key={idx} className="flex gap-2 items-center mb-2">
                <input type="text" placeholder="Description" value={a.description} onChange={updateAllowance(idx, "description")} disabled={submitting} className={`${inputClass} flex-1`} />
                <input type="number" placeholder="Amount $" min="0" value={a.amount} onChange={updateAllowance(idx, "amount")} disabled={submitting} className={`${inputClass} w-32`} />
                <button type="button" onClick={() => removeAllowance(idx)} disabled={submitting} className="text-red-600 dark:text-red-400">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={addAllowance} disabled={submitting} className="tt-btn-secondary text-xs px-3 py-1.5 rounded-xl flex items-center gap-1">
              <Plus className="w-3.5 h-3.5" /> Add Allowance
            </button>
          </div>

          <div>
            <label className={labelClass}>Exclusions</label>
            {exclusions.map((x, idx) => (
              <div key={idx} className="flex gap-2 items-center mb-2">
                <input type="text" placeholder="What's not included" value={x.description} onChange={updateExclusion(idx)} disabled={submitting} className={`${inputClass} flex-1`} />
                <button type="button" onClick={() => removeExclusion(idx)} disabled={submitting} className="text-red-600 dark:text-red-400">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={addExclusion} disabled={submitting} className="tt-btn-secondary text-xs px-3 py-1.5 rounded-xl flex items-center gap-1">
              <Plus className="w-3.5 h-3.5" /> Add Exclusion
            </button>
          </div>

          <div>
            <label className={labelClass}>Payment Schedule</label>
            {paymentSchedule.map((m, idx) => (
              <div key={idx} className="flex gap-2 items-center mb-2">
                <input type="text" placeholder="Milestone" value={m.milestone} onChange={updateMilestone(idx, "milestone")} disabled={submitting} className={`${inputClass} flex-1`} />
                <input type="number" placeholder="%" min="0" max="100" value={m.percent} onChange={updateMilestone(idx, "percent")} disabled={submitting} className={`${inputClass} w-24`} />
                <button type="button" onClick={() => removeMilestone(idx)} disabled={submitting} className="text-red-600 dark:text-red-400">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={addMilestone} disabled={submitting} className="tt-btn-secondary text-xs px-3 py-1.5 rounded-xl flex items-center gap-1">
              <Plus className="w-3.5 h-3.5" /> Add Milestone
            </button>
          </div>

          <div>
            <label className={labelClass}>Additional Notes</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} disabled={submitting} rows={3} className={inputClass} />
          </div>

          <div className="flex items-center gap-3 pt-4 border-t border-slate-100 dark:border-slate-700/80">
            <button
              type="submit"
              disabled={submitting || licenses.length === 0}
              className="tt-btn-primary text-xs px-5 py-2.5 rounded-xl disabled:opacity-50"
            >
              {submitting ? "Submitting…" : "Submit Bid"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
