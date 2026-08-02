/**
 * useVoiceInput.js
 * One shared voice-dictation state machine, replacing 5 independent
 * copy-pasted implementations (kickoff form fields, kickoff chat, the
 * compliance-assistant query box, the debug query page, room design) that
 * had each drifted into a different subset of bugs: a hardcoded mic icon
 * color with no listening state, inconsistent "no speech" error mapping
 * (the plugin emitted two different strings for the same condition and
 * different call sites only checked one of them), and a self-contradictory
 * "Voice input not supported: no speech detected" message.
 *
 * Callers own what happens with a transcript (replace vs. append) via
 * onTranscript, and where an error is surfaced (this hook's own `error`, or
 * a page's existing error banner) via the optional onError; this hook owns
 * only the shared state machine and error mapping.
 */

import { useCallback, useState } from "react";

const ERROR_MESSAGES = {
  "not-allowed": "Microphone access denied. Enable it in your browser or device settings.",
  "permission-denied": "Microphone access denied. Enable it in your browser or device settings.",
  network: "Voice input requires an active internet connection.",
  "no-speech": "Didn't catch that — try again.",
};

/** Exported (not just used internally) so it's unit-testable without
 * rendering a hook -- this mapping is the actual bug surface the 5
 * duplicated implementations kept getting wrong in different ways. */
export function friendlyMessage(code) {
  return ERROR_MESSAGES[code] || `Voice input failed: ${code}`;
}

/**
 * @param {{
 *   onTranscript?: (transcript: string) => void,
 *   onError?: (message: string, code: string) => void,
 * }} [options]
 */
export function useVoiceInput({ onTranscript, onError } = {}) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const [errorCode, setErrorCode] = useState("");

  const clearError = useCallback(() => {
    setError("");
    setErrorCode("");
  }, []);

  const startListening = useCallback(async () => {
    setListening(true);
    clearError();
    try {
      const { startSpeechRecognition } = await import("../services/roomCapture.js");
      const res = await startSpeechRecognition();
      if (res.transcript) {
        onTranscript?.(res.transcript);
      } else if (res.error) {
        const message = friendlyMessage(res.error);
        setErrorCode(res.error);
        setError(message);
        onError?.(message, res.error);
      }
    } catch (err) {
      // Only reachable if the dynamic import itself fails, or a native
      // (Capacitor/iOS) promise rejects -- the web path above always
      // resolves with {transcript, error}, never throws.
      const message = err.message || "Voice input isn't available right now.";
      setErrorCode("unavailable");
      setError(message);
      onError?.(message, "unavailable");
    } finally {
      setListening(false);
    }
  }, [onTranscript, onError, clearError]);

  return { listening, error, errorCode, startListening, clearError };
}
