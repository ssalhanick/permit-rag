import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Gavel } from "lucide-react";
import { awardBid, fetchProjectBids, setProjectMarketplaceStatus } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";
import BidComparisonView from "../../bids/BidComparisonView.jsx";

const STATUS_LABELS = {
  unlisted: "Not listed",
  open: "Open for bidding",
  awarded: "Awarded",
  closed: "Closed",
};

const STATUS_BADGE_CLASS = {
  open: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800",
  awarded: "bg-blue-100 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300 border-blue-300 dark:border-blue-800",
};
const DEFAULT_BADGE_CLASS =
  "bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300 border-slate-300 dark:border-slate-700";

/** Homeowner-facing bidding controls: open/close toggle, incoming bids with
 * evaluator scoring, and the award action. */
export default function ProjectBiddingPage() {
  const { project, setProject, role, projectId } = useProject();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [bids, setBids] = useState([]);
  const [loadingBids, setLoadingBids] = useState(false);
  const [awardingBidId, setAwardingBidId] = useState(null);

  const isOwner = role === "owner";
  const status = project?.marketplace_status || "unlisted";
  const canSeeBids = status === "open" || status === "awarded" || status === "closed";

  const loadBids = useCallback(async () => {
    if (!canSeeBids) {
      setBids([]);
      return;
    }
    setLoadingBids(true);
    try {
      const res = await fetchProjectBids(projectId);
      setBids(res.data || []);
    } catch (err) {
      setError(err.message || "Failed to load bids.");
    } finally {
      setLoadingBids(false);
    }
  }, [projectId, canSeeBids]);

  useEffect(() => {
    loadBids();
  }, [loadBids]);

  const handleToggle = async () => {
    setError("");
    setSaving(true);
    try {
      const next = status === "open" ? "unlisted" : "open";
      const res = await setProjectMarketplaceStatus(projectId, next);
      setProject(res.data);
    } catch (err) {
      setError(err.message || "Failed to update bidding status.");
    } finally {
      setSaving(false);
    }
  };

  const handleAward = async (bid) => {
    setError("");
    setAwardingBidId(bid.id);
    try {
      await awardBid(projectId, bid.id);
      const fresh = await fetchProjectBids(projectId);
      setBids(fresh.data || []);
      // The award endpoint returns the bid, not the project — patch the
      // project's status locally rather than issuing a second fetch.
      setProject((p) => (p ? { ...p, marketplace_status: "awarded", awarded_bid_id: bid.id } : p));
    } catch (err) {
      setError(err.message || "Failed to award this bid.");
    } finally {
      setAwardingBidId(null);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6">
      <div className="mb-6 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
          <Gavel className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">Bidding</h1>
          <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
            Open this project so contractors can browse it and submit bids.
          </p>
        </div>
      </div>

      {error && (
        <div className="p-4 mb-6 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm mb-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
              Status
            </div>
            <span
              className={`px-3 py-1 rounded-full text-xs font-semibold border ${STATUS_BADGE_CLASS[status] || DEFAULT_BADGE_CLASS}`}
            >
              {STATUS_LABELS[status] || status}
            </span>
          </div>

          {isOwner && (status === "unlisted" || status === "open") && (
            <button
              type="button"
              onClick={handleToggle}
              disabled={saving}
              className="tt-btn-primary text-xs px-5 py-2.5 rounded-xl disabled:opacity-50"
            >
              {saving ? "Saving…" : status === "open" ? "Close Bidding" : "Open for Bidding"}
            </button>
          )}
        </div>

        {!isOwner && (
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-4">
            Only the project owner can open or close bidding.
          </p>
        )}
        {status === "awarded" && (
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-4">
            A contractor has been awarded this project. Bidding is closed.
          </p>
        )}
      </div>

      {canSeeBids && (
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-3">
            Bids{bids.length > 0 ? ` (${bids.length})` : ""}
          </h2>
          {loadingBids ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading bids…</p>
          ) : (
            <BidComparisonView
              bids={bids}
              onAward={isOwner && status === "open" ? handleAward : null}
              awardingBidId={awardingBidId}
            />
          )}
        </div>
      )}
    </div>
  );
}
