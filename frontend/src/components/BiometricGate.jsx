import { useCallback, useEffect, useState } from "react";
import { BiometricAuth } from "@aparajita/capacitor-biometric-auth";
import { Preferences } from "@capacitor/preferences";
import { isNativePlatform } from "../platform.js";

const BIOMETRIC_PREF = "biometric_gate_enabled";

/**
 * useBiometricGate — optional Face ID / fingerprint re-auth on native resume.
 *
 * @returns {{ enabled: boolean, verified: boolean, promptBiometric: () => Promise<boolean> }}
 */
export function useBiometricGate() {
  const [enabled, setEnabled] = useState(false);
  const [verified, setVerified] = useState(!isNativePlatform());

  useEffect(() => {
    if (!isNativePlatform()) {
      return;
    }
    Preferences.get({ key: BIOMETRIC_PREF }).then(({ value }) => {
      const on = value === "true";
      setEnabled(on);
      setVerified(!on);
    });
  }, []);

  const promptBiometric = useCallback(async () => {
    if (!isNativePlatform()) {
      return true;
    }
    try {
      await BiometricAuth.authenticate({
        reason: "Unlock Permit RAG",
        cancelTitle: "Use password",
      });
      setVerified(true);
      return true;
    } catch {
      return false;
    }
  }, []);

  return { enabled, verified, promptBiometric, setEnabled };
}

/**
 * BiometricGate — blocks children until biometric passes when enabled.
 */
export default function BiometricGate({ children }) {
  const { enabled, verified, promptBiometric } = useBiometricGate();

  useEffect(() => {
    if (enabled && !verified && isNativePlatform()) {
      promptBiometric();
    }
  }, [enabled, verified, promptBiometric]);

  if (enabled && !verified && isNativePlatform()) {
    return (
      <main className="page auth-page">
        <section className="panel auth-panel">
          <h2>Unlock app</h2>
          <p className="muted">Use Face ID or fingerprint to continue.</p>
          <button type="button" className="primary-button" onClick={() => promptBiometric()}>
            Unlock
          </button>
        </section>
      </main>
    );
  }

  return children;
}
