import React, { useState } from "react";
import { Navigate } from "react-router-dom";
import { AlertTriangle, HardHat } from "lucide-react";
import { createContractorProfile } from "../../api.js";
import { useAuth } from "../../context/AuthContext.jsx";
import { SERVICE_MUNICIPALITIES, TRADES } from "../contractorOptions.js";

const EMPTY_FORM = {
  business_name: "",
  contact_name: "",
  phone: "",
  trades: [],
  service_municipalities: [],
  bio: "",
  years_in_business: "",
};

const inputClass =
  "w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50";
const labelClass = "block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5";

function TogglePill({ active, disabled, onClick, children }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors disabled:opacity-50 ${
        active
          ? "bg-blue-600 border-blue-600 text-white"
          : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * Creates the caller's contractor profile. Once created, ContractorRoute
 * lets them into the /contractor/* shell — this page itself has no guard,
 * any authenticated user without a profile yet can reach it.
 */
export default function ContractorOnboardingPage() {
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  if (user?.has_contractor_profile || done) {
    return <Navigate to="/contractor/licenses" replace />;
  }

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const toggleValue = (key, value) => {
    setForm((f) => {
      const current = f[key];
      const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
      return { ...f, [key]: next };
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.business_name.trim()) {
      setError("Business name is required.");
      return;
    }
    setSaving(true);
    try {
      await createContractorProfile({
        business_name: form.business_name.trim(),
        contact_name: form.contact_name.trim() || null,
        phone: form.phone.trim() || null,
        trades: form.trades,
        service_municipalities: form.service_municipalities,
        bio: form.bio.trim() || null,
        years_in_business: form.years_in_business ? Number(form.years_in_business) : null,
      });
      await refreshUser();
      setDone(true);
    } catch (err) {
      setError(err.message || "Failed to create contractor profile.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6">
      <div className="mb-6 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
          <HardHat className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
            Become a Contractor
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
            Create your contractor profile to browse open projects and submit bids.
          </p>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm">
        {error && (
          <div className="p-4 mb-6 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className={labelClass}>Business Name *</label>
            <input
              type="text"
              value={form.business_name}
              onChange={setField("business_name")}
              disabled={saving}
              className={inputClass}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label className={labelClass}>Contact Name</label>
              <input
                type="text"
                value={form.contact_name}
                onChange={setField("contact_name")}
                disabled={saving}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Phone</label>
              <input
                type="tel"
                value={form.phone}
                onChange={setField("phone")}
                disabled={saving}
                className={inputClass}
              />
            </div>
          </div>

          <div>
            <label className={labelClass}>Trades</label>
            <div className="flex flex-wrap gap-2">
              {TRADES.map((trade) => (
                <TogglePill
                  key={trade}
                  active={form.trades.includes(trade)}
                  disabled={saving}
                  onClick={() => toggleValue("trades", trade)}
                >
                  {trade}
                </TogglePill>
              ))}
            </div>
          </div>

          <div>
            <label className={labelClass}>Municipalities Served</label>
            <div className="flex flex-wrap gap-2">
              {SERVICE_MUNICIPALITIES.map((m) => (
                <TogglePill
                  key={m.id}
                  active={form.service_municipalities.includes(m.id)}
                  disabled={saving}
                  onClick={() => toggleValue("service_municipalities", m.id)}
                >
                  {m.label}
                </TogglePill>
              ))}
            </div>
          </div>

          <div>
            <label className={labelClass}>Years in Business</label>
            <input
              type="number"
              min="0"
              max="150"
              value={form.years_in_business}
              onChange={setField("years_in_business")}
              disabled={saving}
              className={`${inputClass} sm:w-40`}
            />
          </div>

          <div>
            <label className={labelClass}>Bio</label>
            <textarea
              value={form.bio}
              onChange={setField("bio")}
              disabled={saving}
              rows={3}
              placeholder="Tell homeowners about your business."
              className={inputClass}
            />
          </div>

          <div className="flex items-center gap-3 pt-4 border-t border-slate-100 dark:border-slate-700/80">
            <button
              type="submit"
              disabled={saving}
              className="tt-btn-primary text-xs flex items-center gap-1.5 px-5 py-2.5 rounded-xl disabled:opacity-50"
            >
              {saving ? "Creating…" : "Create Contractor Profile"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
