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

  async startSpeechRecognition() {
    const SpeechClass = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechClass) {
      return { transcript: "", error: "Speech requires native build or a browser supporting Web Speech API." };
    }
    return new Promise((resolve) => {
      const recognition = new SpeechClass();
      recognition.lang = "en-US";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        resolve({ transcript: text });
      };
      recognition.onerror = (err) => {
        resolve({ transcript: "", error: err.error || "Speech error" });
      };
      recognition.onend = () => {
        // Fallback if no result fired
        setTimeout(() => resolve({ transcript: "", error: "No speech detected" }), 100);
      };
      recognition.start();
    });
  }

  async isAvailable() {
    return { available: false };
  }
}
