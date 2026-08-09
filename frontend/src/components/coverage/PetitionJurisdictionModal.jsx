import React, { useState } from "react";
import { X, Send, Building2, Link2, CheckCircle2, ShieldAlert, Sparkles } from "lucide-react";

/**
 * PetitionJurisdictionModal
 * Allows marketing visitors & contractors to request immediate onboarding of their city or ordinance.
 */
export default function PetitionJurisdictionModal({
  isOpen,
  onClose,
  prefilledJurisdiction = null,
}) {
  const [cityName, setCityName] = useState(prefilledJurisdiction?.name || "");
  const [stateName, setStateName] = useState(prefilledJurisdiction?.state || "Texas");
  const [email, setEmail] = useState("");
  const [ordinanceUrl, setOrdinanceUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [isSubmitted, setIsSubmitted] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    setIsSubmitted(true);
    // Auto close after 3 seconds if needed
  };

  const handleReset = () => {
    setIsSubmitted(false);
    setCityName("");
    setOrdinanceUrl("");
    setNotes("");
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="relative w-full max-w-lg bg-card rounded-2xl border border-border shadow-2xl overflow-hidden p-6 sm:p-8 space-y-6">
        {/* Close Button */}
        <button
          type="button"
          onClick={handleReset}
          className="absolute top-4 right-4 p-2 text-muted-foreground hover:text-foreground rounded-lg hover:bg-secondary transition-colors"
          aria-label="Close modal"
        >
          <X className="w-5 h-5" />
        </button>

        {isSubmitted ? (
          <div className="text-center py-6 space-y-4">
            <div className="w-14 h-14 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto border border-emerald-500/20">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <h3 className="text-xl font-bold text-foreground">Jurisdiction Petition Queued!</h3>
            <p className="text-sm text-muted-foreground max-w-sm mx-auto">
              Thank you! Our automated crawler and municipal compliance team will harvest and index <strong>{cityName || "your requested municipality"}</strong> into the Permit RAG knowledge base.
            </p>
            <button
              type="button"
              onClick={handleReset}
              className="tt-btn-primary px-6 py-2 text-xs"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                <Sparkles className="w-3 h-3" />
                Request Coverage Expansion
              </div>
              <h3 className="text-xl font-extrabold text-foreground">
                Petition a New Municipality
              </h3>
              <p className="text-xs text-muted-foreground">
                Need building code and zoning RAG for a city not yet listed? Submit your target jurisdiction and we'll prioritize its ingestion.
              </p>
            </div>

            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-foreground mb-1">
                    City / Municipality <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Arlington, Southlake, Denton"
                    value={cityName}
                    onChange={(e) => setCityName(e.target.value)}
                    className="tt-input w-full px-3 py-2 text-xs rounded-xl"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-foreground mb-1">
                    State <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="Texas"
                    value={stateName}
                    onChange={(e) => setStateName(e.target.value)}
                    className="tt-input w-full px-3 py-2 text-xs rounded-xl"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-foreground mb-1">
                  Your Work Email (to get notified when live) <span className="text-rose-500">*</span>
                </label>
                <input
                  type="email"
                  required
                  placeholder="contractor@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="tt-input w-full px-3 py-2 text-xs rounded-xl"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-foreground mb-1">
                  Ordinance or Portal Link (Optional)
                </label>
                <div className="relative">
                  <Link2 className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="url"
                    placeholder="https://municode.com/tx/yourcity or cityhall portal"
                    value={ordinanceUrl}
                    onChange={(e) => setOrdinanceUrl(e.target.value)}
                    className="tt-input w-full pl-9 pr-3 py-2 text-xs rounded-xl"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-foreground mb-1">
                  Project Details or Urgency (Optional)
                </label>
                <textarea
                  rows={2}
                  placeholder="e.g. Commercial remodel in progress, need fire sprinkler and setback rules."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="tt-input w-full px-3 py-2 text-xs rounded-xl"
                />
              </div>
            </div>

            <div className="pt-2 flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={handleReset}
                className="tt-btn-secondary px-4 py-2 text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="tt-btn-primary px-5 py-2 text-xs flex items-center gap-1.5 shadow-md shadow-blue-500/20"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Submit Coverage Petition</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
