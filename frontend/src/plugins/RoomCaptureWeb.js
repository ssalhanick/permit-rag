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

  async isAvailable() {
    return { available: false };
  }
}
