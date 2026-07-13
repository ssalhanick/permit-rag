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
    ]

    #if canImport(RoomPlan)
    private var activePresenter: RoomCapturePresenter?
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
}
