/**
 * RoomCaptureWeb — web stub; native RoomPlan plugin required on device.
 */
export class RoomCaptureWeb {
  async startCapture(options) {
    return {
      schema_version: "1.0",
      room_label: options?.room_label || "room",
      captured_at: new Date().toISOString(),
      units: "meters",
      surfaces: [],
      error: "Room capture requires native iOS/Android build with RoomCapture plugin.",
    };
  }

  async startStructureCapture() {
    return {
      schema_version: "2.0",
      scan_type: "structure",
      rooms: [],
      error: "Structure capture requires native iOS build.",
    };
  }

  async openRoomAR() {
    return { opened: false, error: "AR viewer requires native iOS build." };
  }

  async applyMaterial() {
    return { applied: false };
  }

  async previewRoomModel() {
    return { previewed: false, error: "3D model preview requires native iOS build." };
  }

  async startSpeechRecognition() {
    const SpeechClass = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechClass) {
      return { transcript: "", error: "Speech requires native build or a browser supporting Web Speech API." };
    }

    // Explicitly request mic permission — triggers browser dialog on first use.
    // getUserMedia resolves instantly if already granted, throws if denied.
    if (navigator.mediaDevices?.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Stop the tracks immediately — we only needed the permission grant.
        stream.getTracks().forEach((t) => t.stop());
      } catch (err) {
        const code = err.name === "NotAllowedError" ? "not-allowed" : err.name;
        return { transcript: "", error: code };
      }
    }

    return new Promise((resolve) => {
      const recognition = new SpeechClass();
      recognition.lang = "en-US";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      let resolved = false;
      const done = (val) => { if (!resolved) { resolved = true; resolve(val); } };
      recognition.onresult = (event) => {
        done({ transcript: event.results[0][0].transcript });
      };
      recognition.onerror = (err) => {
        done({ transcript: "", error: err.error || "Speech error" });
      };
      recognition.onend = () => {
        // Fallback if no result fired. Uses the same "no-speech" code the
        // browser's own onerror event uses (not a human sentence) -- callers
        // used to check for the two forms inconsistently, which is exactly
        // why "no speech" sometimes leaked through as a raw, confusing
        // string and sometimes silently vanished. One code, mapped to one
        // friendly message in one place (useVoiceInput).
        setTimeout(() => done({ transcript: "", error: "no-speech" }), 100);
      };
      recognition.start();
    });
  }

  async isAvailable() {
    return { available: false };
  }
}
