import Foundation
import Capacitor
import AVFoundation

#if canImport(RoomPlan)
import RoomPlan

enum RoomCapturePermission {
  static func requestCameraAccess(completion: @escaping (Bool) -> Void) {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized:
      completion(true)
    case .notDetermined:
      AVCaptureDevice.requestAccess(for: .video, completionHandler: completion)
    default:
      completion(false)
    }
  }
}
#endif

@objc(RoomCapturePlugin)
public class RoomCapturePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "RoomCapturePlugin"
    public let jsName = "RoomCapture"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isAvailable", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "startCapture", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "startStructureCapture", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "openRoomAR", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "applyMaterial", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "startSpeechRecognition", returnType: CAPPluginReturnPromise),
    ]

    #if canImport(RoomPlan)
    private var activePresenter: RoomCapturePresenter?
    private var activeStructurePresenter: StructureCapturePresenter?
    private var activeARPresenters: [String: RoomARPresenter] = [:]
    #endif

    @objc func isAvailable(_ call: CAPPluginCall) {
        #if canImport(RoomPlan)
        let supported = RoomPlanSupport.isAvailable()
        call.resolve([
            "available": supported,
            "reason": supported ? "" : RoomPlanSupport.unavailableReason(),
        ])
        #else
        call.resolve([
            "available": false,
            "reason": "RoomPlan requires iOS 16+ on a LiDAR-equipped device.",
        ])
        #endif
    }

    @objc func startCapture(_ call: CAPPluginCall) {
        let label = call.getString("room_label") ?? "room"

        #if canImport(RoomPlan)
        guard RoomPlanSupport.isAvailable() else {
            call.reject(RoomPlanSupport.unavailableReason())
            return
        }

        guard let viewController = bridge?.viewController else {
            call.reject("No view controller available for room capture.")
            return
        }

        RoomCapturePermission.requestCameraAccess { granted in
            DispatchQueue.main.async {
                guard granted else {
                    call.reject("Camera permission is required for room scanning. Enable it in Settings → Permit RAG.")
                    return
                }

                let presenter = RoomCapturePresenter(call: call, roomLabel: label) { [weak self] in
                    self?.activePresenter = nil
                }
                self.activePresenter = presenter
                presenter.present(from: viewController)
            }
        }
        #else
        call.reject("RoomPlan requires iOS 16+ on a LiDAR-equipped device.")
        #endif
    }

    @objc func startStructureCapture(_ call: CAPPluginCall) {
        let label = call.getString("structure_label") ?? "Whole house"

        #if canImport(RoomPlan)
        guard RoomPlanSupport.isAvailable() else {
            call.reject(RoomPlanSupport.unavailableReason())
            return
        }
        guard let viewController = bridge?.viewController else {
            call.reject("No view controller available for structure capture.")
            return
        }

        RoomCapturePermission.requestCameraAccess { granted in
            DispatchQueue.main.async {
                guard granted else {
                    call.reject("Camera permission is required for structure scanning.")
                    return
                }
                let presenter = StructureCapturePresenter(call: call, structureLabel: label) { [weak self] in
                    self?.activeStructurePresenter = nil
                }
                self.activeStructurePresenter = presenter
                presenter.present(from: viewController)
            }
        }
        #else
        call.reject("Structure capture requires iOS 16+ RoomPlan.")
        #endif
    }

    @objc func openRoomAR(_ call: CAPPluginCall) {
        #if canImport(RoomPlan)
        guard let projectId = call.getString("projectId"),
              let structureId = call.getString("structureId"),
              let roomId = call.getString("roomId"),
              let viewController = bridge?.viewController else {
            call.reject("projectId, structureId, and roomId are required.")
            return
        }
        let roomLabel = call.getString("roomLabel") ?? "Room"
        let presenter = RoomARPresenter(
            call: call,
            projectId: projectId,
            structureId: structureId,
            roomId: roomId,
            roomLabel: roomLabel
        )
        activeARPresenters[roomId] = presenter
        presenter.present(from: viewController)
        #else
        call.reject("AR viewer requires iOS RoomPlan build.")
        #endif
    }

    @objc func applyMaterial(_ call: CAPPluginCall) {
        #if canImport(RoomPlan)
        guard let projectId = call.getString("projectId"),
              let structureId = call.getString("structureId"),
              let roomId = call.getString("roomId") else {
            call.reject("projectId, structureId, and roomId are required.")
            return
        }

        let overlay: [String: Any] = [
            "surface_id": call.getString("surfaceId") as Any,
            "type": call.getString("type") ?? "paint",
            "material_id": call.getString("materialId") ?? "generic_paint",
            "color_hex": call.getString("colorHex") as Any,
            "asset_url": NSNull(),
        ]

        if let presenter = activeARPresenters[roomId] {
            let applied = presenter.applyMaterial(
                surfaceId: call.getString("surfaceId"),
                materialId: call.getString("materialId") ?? "generic_paint",
                colorHex: call.getString("colorHex"),
                type: call.getString("type") ?? "paint"
            )
            call.resolve(["applied": true, "overlay": applied, "persisted": true])
            return
        }

        let redesignPath = RoomScanPaths.redesignPath(
            projectId: projectId,
            structureId: structureId,
            roomId: roomId
        )
        var redesign = RoomScanJSON.read(path: redesignPath) ?? [
            "schema_version": "1.0",
            "scan_id": roomId,
            "overlays": [],
        ]
        var overlays = redesign["overlays"] as? [[String: Any]] ?? []
        overlays.append(overlay)
        redesign["overlays"] = overlays
        redesign["updated_at"] = ISO8601DateFormatter().string(from: Date())
        try? RoomScanJSON.write(path: redesignPath, object: redesign)
        call.resolve(["applied": true, "overlay": overlay, "persisted": true])
        #else
        call.resolve(["applied": false])
        #endif
    }

    @objc func startSpeechRecognition(_ call: CAPPluginCall) {
        #if canImport(RoomPlan)
        guard let viewController = bridge?.viewController else {
            call.reject("No view controller for speech.")
            return
        }
        SpeechCapture.requestAuthorization { granted in
            guard granted else {
                call.reject("Speech permission denied.")
                return
            }
            SpeechCapture.recognize(from: viewController) { result in
                switch result {
                case .success(let transcript):
                    call.resolve(["transcript": transcript])
                case .failure(let error):
                    call.reject(error.localizedDescription)
                }
            }
        }
        #else
        call.reject("Speech requires native iOS build.")
        #endif
    }
}
