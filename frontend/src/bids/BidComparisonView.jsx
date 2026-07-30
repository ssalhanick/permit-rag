import React from "react";
import BidCard from "./BidCard.jsx";

/**
 * Stacked comparison of a project's bids (homeowner-facing), each with its
 * Bid Evaluator scoring so competing bids can be judged side by side.
 */
export default function BidComparisonView({ bids, onAward, awardingBidId }) {
  if (!bids || bids.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-8 text-center text-sm text-slate-500 dark:text-slate-400">
        No bids yet.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {bids.map((bid) => (
        <BidCard key={bid.id} bid={bid} onAward={onAward} awarding={awardingBidId === bid.id} />
      ))}
    </div>
  );
}
