import React from "react";
import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

const SEVERITY_CLASS = {
  high: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-300 border-red-300 dark:border-red-800",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 border-amber-300 dark:border-amber-800",
  low: "bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300 border-slate-300 dark:border-slate-700",
};

function completenessBadgeClass(score) {
  if (score >= 0.9) {
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800";
  }
  if (score >= 0.6) {
    return "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 border-amber-300 dark:border-amber-800";
  }
  return "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-300 border-red-300 dark:border-red-800";
}

/**
 * Scored-badge summary for one bid's Bid Evaluator report (completeness,
 * deterministic red flags, and LLM-assisted novel flags).
 */
export default function BidEvaluationBadges({ evaluation, compact = false }) {
  if (!evaluation) {
    return null;
  }
  const flagCount = (evaluation.red_flags?.length || 0) + (evaluation.llm_flags?.length || 0);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border flex items-center gap-1 ${completenessBadgeClass(evaluation.completeness_score)}`}
        >
          <CheckCircle2 className="w-3 h-3" />
          {Math.round(evaluation.completeness_score * 100)}% complete
        </span>
        {flagCount > 0 ? (
          <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold border bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 border-amber-300 dark:border-amber-800 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            {flagCount} flag{flagCount === 1 ? "" : "s"}
          </span>
        ) : (
          <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold border bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800 flex items-center gap-1">
            <ShieldAlert className="w-3 h-3" />
            No flags
          </span>
        )}
      </div>

      {!compact && evaluation.missing_clauses?.length > 0 && (
        <p className="text-xs text-slate-500 dark:text-slate-400">Missing: {evaluation.missing_clauses.join(", ")}</p>
      )}

      {!compact && flagCount > 0 && (
        <ul className="space-y-1">
          {evaluation.red_flags.map((flag) => (
            <li
              key={flag.key}
              className={`text-xs px-2.5 py-1.5 rounded-lg border ${SEVERITY_CLASS[flag.severity] || SEVERITY_CLASS.low}`}
            >
              {flag.message}
            </li>
          ))}
          {evaluation.llm_flags.map((flag, idx) => (
            <li
              key={`llm-${idx}`}
              className="text-xs px-2.5 py-1.5 rounded-lg border bg-purple-100 text-purple-800 dark:bg-purple-950/50 dark:text-purple-300 border-purple-300 dark:border-purple-800"
            >
              {flag.label}: {flag.detail}
            </li>
          ))}
        </ul>
      )}

      {!compact && <p className="text-[10px] text-slate-400 dark:text-slate-500 italic">{evaluation.disclaimer}</p>}
    </div>
  );
}
