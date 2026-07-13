import Foundation
import UIKit
import Capacitor
import Speech

#if canImport(RoomPlan)
import RoomPlan
import RealityKit
import ARKit

/// Room-scoped AR design viewer with surface list and material overlays.
final class RoomARPresenter: NSObject, UITableViewDelegate, UITableViewDataSource {
    private let call: CAPPluginCall?
    private let projectId: String
    private let structureId: String
    private let roomId: String
    private let roomLabel: String
    private var capture: [String: Any] = [:]
    private var redesign: [String: Any] = [:]
    private var surfaces: [[String: Any]] = []
    private var arView: ARView?
    private var viewController: UIViewController?

    init(
        call: CAPPluginCall? = nil,
        projectId: String,
        structureId: String,
        roomId: String,
        roomLabel: String
    ) {
        self.call = call
        self.projectId = projectId
        self.structureId = structureId
        self.roomId = roomId
        self.roomLabel = roomLabel
        super.init()
    }

    func present(from host: UIViewController) {
        let capturePath = RoomScanPaths.roomCapturePath(
            projectId: projectId,
            structureId: structureId,
            roomId: roomId
        )
        let redesignPath = RoomScanPaths.redesignPath(
            projectId: projectId,
            structureId: structureId,
            roomId: roomId
        )
        capture = RoomScanJSON.read(path: capturePath) ?? [:]
        redesign = RoomScanJSON.read(path: redesignPath) ?? [
            "schema_version": "1.0",
            "scan_id": roomId,
            "overlays": [],
        ]
        surfaces = capture["surfaces"] as? [[String: Any]] ?? []

        let vc = UIViewController()
        vc.modalPresentationStyle = .fullScreen
        vc.view.backgroundColor = .black

        let arView = ARView(frame: .zero)
        arView.translatesAutoresizingMaskIntoConstraints = false
        arView.automaticallyConfigureSession = true
        vc.view.addSubview(arView)
        self.arView = arView

        let table = UITableView(frame: .zero, style: .insetGrouped)
        table.translatesAutoresizingMaskIntoConstraints = false
        table.delegate = self
        table.dataSource = self
        table.backgroundColor = UIColor.black.withAlphaComponent(0.45)
        vc.view.addSubview(table)

        let close = UIButton(type: .system)
        close.setTitle("Close AR", for: .normal)
        close.tintColor = .white
        close.translatesAutoresizingMaskIntoConstraints = false
        close.addTarget(self, action: #selector(closeTapped), for: .touchUpInside)
        vc.view.addSubview(close)

        NSLayoutConstraint.activate([
            arView.topAnchor.constraint(equalTo: vc.view.topAnchor),
            arView.leadingAnchor.constraint(equalTo: vc.view.leadingAnchor),
            arView.trailingAnchor.constraint(equalTo: vc.view.trailingAnchor),
            arView.heightAnchor.constraint(equalTo: vc.view.heightAnchor, multiplier: 0.55),
            table.topAnchor.constraint(equalTo: arView.bottomAnchor),
            table.leadingAnchor.constraint(equalTo: vc.view.leadingAnchor),
            table.trailingAnchor.constraint(equalTo: vc.view.trailingAnchor),
            table.bottomAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.bottomAnchor, constant: -44),
            close.bottomAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.bottomAnchor, constant: -8),
            close.centerXAnchor.constraint(equalTo: vc.view.centerXAnchor),
        ])

        addWallAnchors(to: arView)
        viewController = vc
        host.present(vc, animated: true) {
            self.call?.resolve(["opened": true, "room_id": self.roomId])
        }
    }

    private func addWallAnchors(to arView: ARView) {
        let anchor = AnchorEntity(world: .zero)
        for (index, surface) in surfaces.enumerated() where (surface["category"] as? String) == "wall" {
            let dims = surface["dimensions"] as? [String: Double] ?? [:]
            let width = Float(dims["width"] ?? 1)
            let height = Float(dims["height"] ?? 2.4)
            let mesh = MeshResource.generatePlane(width: width, height: height)
            var material = SimpleMaterial(color: .white.withAlphaComponent(0.35), isMetallic: false)
            if let overlay = overlayForSurface(surface["id"] as? String) {
                material = materialForOverlay(overlay)
            }
            let entity = ModelEntity(mesh: mesh, materials: [material])
            entity.position = SIMD3<Float>(Float(index) * 0.05, 0, -1.5)
            anchor.addChild(entity)
        }
        arView.scene.addAnchor(anchor)
    }

    private func overlayForSurface(_ surfaceId: String?) -> [String: Any]? {
        guard let surfaceId else { return nil }
        let overlays = redesign["overlays"] as? [[String: Any]] ?? []
        return overlays.last { ($0["surface_id"] as? String) == surfaceId || $0["surface_id"] == nil }
    }

    private func materialForOverlay(_ overlay: [String: Any]) -> SimpleMaterial {
        let hex = overlay["color_hex"] as? String ?? "#FFFFFF"
        return SimpleMaterial(color: UIColor(hex: hex) ?? .white, isMetallic: overlay["type"] as? String == "appliance")
    }

    func applyMaterial(surfaceId: String?, materialId: String, colorHex: String?, type: String) -> [String: Any] {
        let overlay: [String: Any] = [
            "surface_id": surfaceId as Any,
            "type": type,
            "material_id": materialId,
            "color_hex": colorHex as Any,
            "asset_url": NSNull(),
        ]
        var overlays = redesign["overlays"] as? [[String: Any]] ?? []
        overlays.append(overlay)
        redesign["overlays"] = overlays
        redesign["updated_at"] = ISO8601DateFormatter().string(from: Date())

        let path = RoomScanPaths.redesignPath(projectId: projectId, structureId: structureId, roomId: roomId)
        try? RoomScanJSON.write(path: path, object: redesign)
        if let arView {
            arView.scene.anchors.removeAll()
            addWallAnchors(to: arView)
        }
        return overlay
    }

    @objc private func closeTapped() {
        viewController?.dismiss(animated: true)
    }

    func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        max(surfaces.count, 1)
    }

    func tableView(_ tableView: UITableView, titleForHeaderInSection section: Int) -> String? {
        "\(roomLabel) — tap wall to apply material"
    }

    func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = tableView.dequeueReusableCell(withIdentifier: "wall") ??
            UITableViewCell(style: .subtitle, reuseIdentifier: "wall")
        if surfaces.isEmpty {
            cell.textLabel?.text = "No surfaces loaded"
            return cell
        }
        let surface = surfaces[indexPath.row]
        let category = surface["category"] as? String ?? "surface"
        let dims = surface["dimensions"] as? [String: Double] ?? [:]
        cell.textLabel?.text = "\(category) \(surface["id"] as? String ?? "")"
        cell.detailTextLabel?.text = String(format: "%.2fm × %.2fm", dims["width"] ?? 0, dims["height"] ?? 0)
        cell.backgroundColor = .secondarySystemBackground
        return cell
    }

    func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        tableView.deselectRow(at: indexPath, animated: true)
        guard indexPath.row < surfaces.count else { return }
        let surface = surfaces[indexPath.row]
        let alert = UIAlertController(title: "Apply material", message: nil, preferredStyle: .actionSheet)
        for preset in MaterialCatalog.presets {
            alert.addAction(UIAlertAction(title: preset.label, style: .default) { _ in
                _ = self.applyMaterial(
                    surfaceId: surface["id"] as? String,
                    materialId: preset.id,
                    colorHex: preset.colorHex,
                    type: preset.type
                )
                tableView.reloadData()
            })
        }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        viewController?.present(alert, animated: true)
    }
}

enum MaterialCatalog {
    struct Preset {
        let id: String
        let type: String
        let label: String
        let colorHex: String
    }

    static let presets: [Preset] = [
        Preset(id: "generic_paint", type: "paint", label: "Generic paint", colorHex: "#FFFFFF"),
        Preset(id: "white_subway_tile", type: "tile", label: "White subway tile", colorHex: "#F8F8F8"),
        Preset(id: "sage_green_paint", type: "paint", label: "Sage green", colorHex: "#9CAF88"),
        Preset(id: "white_trim", type: "trim", label: "White trim", colorHex: "#FFFFFF"),
        Preset(id: "stainless_appliance", type: "appliance", label: "Stainless appliance", colorHex: "#C0C0C0"),
    ]
}

extension UIColor {
    convenience init?(hex: String) {
        var cleaned = hex.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        if cleaned.hasPrefix("#") { cleaned.removeFirst() }
        guard cleaned.count == 6, let value = UInt64(cleaned, radix: 16) else { return nil }
        self.init(
            red: CGFloat((value & 0xFF0000) >> 16) / 255,
            green: CGFloat((value & 0x00FF00) >> 8) / 255,
            blue: CGFloat(value & 0x0000FF) / 255,
            alpha: 1
        )
    }
}

enum SpeechCapture {
    static func requestAuthorization(completion: @escaping (Bool) -> Void) {
        SFSpeechRecognizer.requestAuthorization { status in
            DispatchQueue.main.async {
                completion(status == .authorized)
            }
        }
    }

    static func recognize(from presenter: UIViewController, completion: @escaping (Result<String, Error>) -> Void) {
        guard let recognizer = SFSpeechRecognizer(), recognizer.isAvailable else {
            completion(.failure(NSError(domain: "Speech", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "Speech recognition unavailable.",
            ])))
            return
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = false
        let audioEngine = AVAudioEngine()

        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.record, mode: .measurement, options: .duckOthers)
        try? session.setActive(true, options: .notifyOthersOnDeactivation)

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }
        audioEngine.prepare()
        try? audioEngine.start()

        recognizer.recognitionTask(with: request) { result, error in
            if let error {
                audioEngine.stop()
                input.removeTap(onBus: 0)
                completion(.failure(error))
                return
            }
            if let result, result.isFinal {
                audioEngine.stop()
                input.removeTap(onBus: 0)
                completion(.success(result.bestTranscription.formattedString))
            }
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) {
            audioEngine.stop()
            input.removeTap(onBus: 0)
            request.endAudio()
        }
    }
}
#endif

import AVFoundation
