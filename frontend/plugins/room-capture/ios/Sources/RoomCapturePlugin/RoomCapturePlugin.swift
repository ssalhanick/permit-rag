import Foundation
import Capacitor

@objc(RoomCapturePlugin)
public class RoomCapturePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "RoomCapturePlugin"
    public let jsName = "RoomCapture"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isAvailable", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "startCapture", returnType: CAPPluginReturnPromise),
    ]

    @objc func isAvailable(_ call: CAPPluginCall) {
        #if canImport(RoomPlan)
        call.resolve(["available": true])
        #else
        call.resolve(["available": false])
        #endif
    }

    @objc func startCapture(_ call: CAPPluginCall) {
        let label = call.getString("room_label") ?? "room"
        #if canImport(RoomPlan)
        call.resolve([
            "schema_version": "1.0",
            "room_label": label,
            "units": "meters",
            "surfaces": [],
            "error": "RoomPlan capture UI — wire CapturedRoom export in native sprint.",
        ])
        #else
        call.resolve([
            "schema_version": "1.0",
            "room_label": label,
            "units": "meters",
            "surfaces": [],
            "error": "RoomPlan requires LiDAR-equipped iPhone.",
        ])
        #endif
    }
}
