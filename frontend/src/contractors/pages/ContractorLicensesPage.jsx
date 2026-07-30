import React, { useEffect, useState } from "react";
import { AlertTriangle, BadgeCheck, Plus, Trash2 } from "lucide-react";
import {
  createContractorLicense,
  deleteContractorLicense,
  fetchContractorLicenses,
  updateContractorLicense,
} from "../../api.js";
import { TRADES } from "../contractorOptions.js";

const inputClass =
  "w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50";
const labelClass = "block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5";

const EMPTY_FORM = {
  trade: TRADES[0],
  license_number: "",
  expiration_date: "",
  issuing_authority: "",
  insurance_provider: "",
  insurance_policy_number: "",
  insurance_coverage_amount: "",
  insurance_expiration_date: "",
};

/** Color-coded expiration badge — green >60d, amber 15-60d, red <15d or expired. */
function expirationBadge(expirationDate) {
  const days = Math.ceil((new Date(`${expirationDate}T00:00:00`) - new Date()) / (1000 * 60 * 60 * 24));
  if (days < 0) {
    return { text: "Expired", className: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-300 border-red-300 dark:border-red-800" };
  }
  if (days < 15) {
    return { text: `Expires in ${days}d`, className: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-300 border-red-300 dark:border-red-800" };
  }
  if (days < 60) {
    return { text: `Expires in ${days}d`, className: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 border-amber-300 dark:border-amber-800" };
  }
  return { text: `Expires ${expirationDate}`, className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800" };
}

export default function ContractorLicensesPage() {
  const [licenses, setLicenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await fetchContractorLicenses();
      setLicenses(res.data || []);
    } catch (err) {
      setError(err.message || "Failed to load licenses.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleAdd = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.license_number.trim() || !form.expiration_date) {
      setError("License number and expiration date are required.");
      return;
    }
    setSaving(true);
    try {
      await createContractorLicense({
        trade: form.trade,
        license_number: form.license_number.trim(),
        expiration_date: form.expiration_date,
        issuing_authority: form.issuing_authority.trim() || null,
        insurance_provider: form.insurance_provider.trim() || null,
        insurance_policy_number: form.insurance_policy_number.trim() || null,
        insurance_coverage_amount: form.insurance_coverage_amount ? Number(form.insurance_coverage_amount) : null,
        insurance_expiration_date: form.insurance_expiration_date || null,
      });
      setForm(EMPTY_FORM);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.message || "Failed to add license.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (licenseId) => {
    if (!window.confirm("Remove this license record?")) {
      return;
    }
    try {
      await deleteContractorLicense(licenseId);
      setLicenses((rows) => rows.filter((r) => r.id !== licenseId));
    } catch (err) {
      setError(err.message || "Failed to remove license.");
    }
  };

  const handleRenew = async (license) => {
    const nextDate = window.prompt("New expiration date (YYYY-MM-DD):", license.expiration_date);
    if (!nextDate) {
      return;
    }
    try {
      const res = await updateContractorLicense(license.id, { expiration_date: nextDate });
      setLicenses((rows) => rows.map((r) => (r.id === license.id ? res.data : r)));
    } catch (err) {
      setError(err.message || "Failed to update license.");
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6">
      <div className="mb-6 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
            <BadgeCheck className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
              Licenses &amp; Insurance
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
              A current, non-expired license is required before you can submit a bid.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowForm((v) => !v)}
          className="tt-btn-primary text-xs flex items-center gap-1.5 px-4 py-2.5 rounded-xl"
        >
          <Plus className="w-4 h-4" />
          Add License
        </button>
      </div>

      {error && (
        <div className="p-4 mb-6 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {showForm && (
        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm mb-6">
          <form onSubmit={handleAdd} className="space-y-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div>
                <label className={labelClass}>Trade</label>
                <select value={form.trade} onChange={setField("trade")} disabled={saving} className={inputClass}>
                  {TRADES.map((trade) => (
                    <option key={trade} value={trade}>
                      {trade}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelClass}>License Number *</label>
                <input
                  type="text"
                  value={form.license_number}
                  onChange={setField("license_number")}
                  disabled={saving}
                  placeholder="e.g. TX12345"
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Expiration Date *</label>
                <input
                  type="date"
                  value={form.expiration_date}
                  onChange={setField("expiration_date")}
                  disabled={saving}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Issuing Authority</label>
                <input
                  type="text"
                  value={form.issuing_authority}
                  onChange={setField("issuing_authority")}
                  disabled={saving}
                  placeholder="e.g. TDLR"
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Insurance Provider</label>
                <input
                  type="text"
                  value={form.insurance_provider}
                  onChange={setField("insurance_provider")}
                  disabled={saving}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Insurance Policy #</label>
                <input
                  type="text"
                  value={form.insurance_policy_number}
                  onChange={setField("insurance_policy_number")}
                  disabled={saving}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Coverage Amount ($)</label>
                <input
                  type="number"
                  min="0"
                  value={form.insurance_coverage_amount}
                  onChange={setField("insurance_coverage_amount")}
                  disabled={saving}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Insurance Expiration</label>
                <input
                  type="date"
                  value={form.insurance_expiration_date}
                  onChange={setField("insurance_expiration_date")}
                  disabled={saving}
                  className={inputClass}
                />
              </div>
            </div>
            <div className="flex items-center gap-3 pt-4 border-t border-slate-100 dark:border-slate-700/80">
              <button
                type="submit"
                disabled={saving}
                className="tt-btn-primary text-xs flex items-center gap-1.5 px-5 py-2.5 rounded-xl disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save License"}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                disabled={saving}
                className="tt-btn-secondary text-xs px-4 py-2.5 rounded-xl disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading licenses…</p>
      ) : licenses.length === 0 ? (
        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-8 text-center text-sm text-slate-500 dark:text-slate-400">
          No licenses on file yet. Add one to become eligible to bid.
        </div>
      ) : (
        <div className="space-y-3">
          {licenses.map((license) => {
            const badge = expirationBadge(license.expiration_date);
            return (
              <div
                key={license.id}
                className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 sm:p-5 shadow-sm flex flex-wrap items-center justify-between gap-3"
              >
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-slate-900 dark:text-slate-100 text-sm">{license.trade}</span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">#{license.license_number}</span>
                    <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${badge.className}`}>
                      {badge.text}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {license.issuing_authority && <span>{license.issuing_authority} · </span>}
                    {license.insurance_provider
                      ? `Insured via ${license.insurance_provider}`
                      : "No insurance on file"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleRenew(license)}
                    className="tt-btn-secondary text-xs px-3 py-2 rounded-xl"
                  >
                    Renew
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(license.id)}
                    className="text-xs px-3 py-2 rounded-xl border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/50 flex items-center gap-1.5"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Remove
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
