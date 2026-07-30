import React from "react";
import BidEvaluationBadges from "./BidEvaluationBadges.jsx";

const STATUS_CLASS = {
  submitted: "bg-blue-100 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300 border-blue-300 dark:border-blue-800",
  awarded: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800",
  declined: "bg-slate-100 text-slate-600 dark:bg-slate-900 dark:text-slate-400 border-slate-300 dark:border-slate-700",
  withdrawn: "bg-slate-100 text-slate-600 dark:bg-slate-900 dark:text-slate-400 border-slate-300 dark:border-slate-700",
};

/**
 * One bid's summary card — used both in the homeowner's comparison list and
 * a contractor's "My Bids" history.
 */
export default function BidCard({ bid, onAward, onWithdraw, awarding = false, showEvaluation = true }) {
  return (
    <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 sm:p-5 shadow-sm space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="font-bold text-slate-900 dark:text-slate-100 text-sm">
            {bid.contractor_business_name || "Unknown contractor"}
          </div>
          <div className="text-xs text-slate-500 dark:text-slate-400">
            ${Number(bid.total_price).toLocaleString()} total
            {bid.labor_total != null && ` · $${Number(bid.labor_total).toLocaleString()} labor`}
            {bid.material_total != null && ` · $${Number(bid.material_total).toLocaleString()} materials`}
          </div>
        </div>
        <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${STATUS_CLASS[bid.status] || STATUS_CLASS.submitted}`}>
          {bid.status}
        </span>
      </div>

      {(bid.timeline_start || bid.timeline_end) && (
        <div className="text-xs text-slate-500 dark:text-slate-400">
          Timeline: {bid.timeline_start || "?"} → {bid.timeline_end || "?"}
        </div>
      )}

      {bid.materials_source !== "unspecified" && (
        <div className="text-xs text-slate-500 dark:text-slate-400">
          Materials: {bid.materials_source.replaceAll("_", " ")}
          {bid.materials_source_notes && ` — ${bid.materials_source_notes}`}
        </div>
      )}

      {showEvaluation && <BidEvaluationBadges evaluation={bid.evaluation} />}

      <div className="flex items-center gap-2">
        {onAward && bid.status === "submitted" && (
          <button
            type="button"
            onClick={() => onAward(bid)}
            disabled={awarding}
            className="tt-btn-primary text-xs px-4 py-2 rounded-xl disabled:opacity-50"
          >
            {awarding ? "Awarding…" : "Award This Bid"}
          </button>
        )}
        {onWithdraw && bid.status === "submitted" && (
          <button
            type="button"
            onClick={() => onWithdraw(bid)}
            className="text-xs px-4 py-2 rounded-xl border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/50"
          >
            Withdraw
          </button>
        )}
      </div>
    </div>
  );
}
