import React from "react";
import { Lock } from "lucide-react";
import { detectBrowserSteps } from "../utils/micPermissionSteps.js";

/**
 * MicPermissionHelp.jsx
 * No browser lets a webpage deep-link into its own per-origin permission
 * settings (blocked cross-browser for anti-abuse reasons — there is no
 * `chrome://settings/...`-equivalent URL a page can navigate to). This is
 * the achievable version: detect the browser and show the exact click-path,
 * instead of a link that can't exist.
 *
 * Render whenever useVoiceInput's errorCode is "not-allowed" or
 * "permission-denied" — renders nothing for any other code.
 */
export default function MicPermissionHelp({ errorCode }) {
  if (errorCode !== "not-allowed" && errorCode !== "permission-denied") {
    return null;
  }
  const steps = detectBrowserSteps();
  return (
    <div className="mic-permission-help" role="alert">
      <div className="mic-permission-help-title">
        <Lock className="w-3.5 h-3.5" aria-hidden="true" />
        Microphone access is blocked
      </div>
      <ol className="mic-permission-help-steps">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </div>
  );
}
