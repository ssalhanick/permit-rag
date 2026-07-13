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
    return { transcript: "", error: "Speech requires native iOS build." };
  }

  async isAvailable() {
    return { available: false };
  }
}
