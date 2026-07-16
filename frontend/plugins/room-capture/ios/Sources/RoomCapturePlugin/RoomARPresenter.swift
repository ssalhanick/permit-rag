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
    private var textureCache: [String: TextureResource] = [:]
    private weak var plugin: RoomCapturePlugin?
    private var dictateButton: UIButton?

    init(
        call: CAPPluginCall? = nil,
        plugin: RoomCapturePlugin? = nil,
        projectId: String,
        structureId: String,
        roomId: String,
        roomLabel: String
    ) {
        self.call = call
        self.plugin = plugin
        self.projectId = projectId
        self.structureId = structureId
        self.roomId = roomId
        self.roomLabel = roomLabel
        super.init()
    }

    func present(from host: UIViewController) {
        if !Thread.isMainThread {
            DispatchQueue.main.async { [weak self] in
                self?.present(from: host)
            }
            return
        }

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
        if (capture["surfaces"] as? [[String: Any]] ?? []).isEmpty {
            if let discovered = discoverCapture(projectId: projectId, roomId: roomId) {
                capture = discovered
            }
        }
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

        let dictate = UIButton(type: .system)
        dictate.setTitle("Dictate Command", for: .normal)
        dictate.tintColor = .systemBlue
        dictate.translatesAutoresizingMaskIntoConstraints = false
        dictate.addTarget(self, action: #selector(dictateTapped), for: .touchUpInside)
        vc.view.addSubview(dictate)
        self.dictateButton = dictate

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
            close.leadingAnchor.constraint(equalTo: vc.view.leadingAnchor, constant: 20),
            dictate.bottomAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.bottomAnchor, constant: -8),
            dictate.trailingAnchor.constraint(equalTo: vc.view.trailingAnchor, constant: -20),
        ])

        addWallAnchors(to: arView)
        viewController = vc
        host.present(vc, animated: true) {
            self.call?.resolve(["opened": true, "room_id": self.roomId])
        }
    }

    private func discoverCapture(projectId: String, roomId: String) -> [String: Any]? {
        let scopes = projectId == "library" ? ["library"] : [projectId, "library"]
        for scope in scopes {
            let scopePath = RoomScanPaths.fileURL(relativePath: "room_scans/\(scope)")
            guard let entries = try? FileManager.default.contentsOfDirectory(
                at: scopePath,
                includingPropertiesForKeys: nil
            ) else {
                continue
            }
            for entry in entries where entry.hasDirectoryPath {
                let structureId = entry.lastPathComponent
                let roomsPath = scopePath.appendingPathComponent("\(structureId)/rooms")
                guard let roomEntries = try? FileManager.default.contentsOfDirectory(
                    at: roomsPath,
                    includingPropertiesForKeys: nil
                ) else {
                    continue
                }
                for roomEntry in roomEntries where roomEntry.hasDirectoryPath {
                    let rId = roomEntry.lastPathComponent
                    if rId.caseInsensitiveCompare(roomId) == .orderedSame {
                        let relative = RoomScanPaths.roomCapturePath(
                            projectId: scope,
                            structureId: structureId,
                            roomId: rId
                        )
                        if let json = RoomScanJSON.read(path: relative),
                           !(json["surfaces"] as? [[String: Any]] ?? []).isEmpty {
                            return json
                        }
                    }
                }
            }
        }
        return nil
    }

    private func addWallAnchors(to arView: ARView) {
        let anchor = AnchorEntity(world: .zero)
        for (index, surface) in surfaces.enumerated() where (surface["category"] as? String) == "wall" {
            let dims = surface["dimensions"] as? [String: Double] ?? [:]
            let width = Float(dims["width"] ?? 1)
            let height = Float(dims["height"] ?? 2.4)
            let mesh = MeshResource.generatePlane(width: width, height: height)
            let overlay = overlayForSurface(surface["id"] as? String)
            let material = materialForOverlay(overlay ?? [:], texture: textureForOverlay(overlay))
            let entity = ModelEntity(mesh: mesh, materials: [material])
            entity.position = SIMD3<Float>(Float(index) * 1.05 - 1.0, 0, -1.8)
            anchor.addChild(entity)
        }
        arView.scene.addAnchor(anchor)
        preloadOverlayTextures()
    }

    private func imageUrlForOverlay(_ overlay: [String: Any]?) -> String? {
        guard let overlay else { return nil }
        if let asset = overlay["asset_url"] as? String, !asset.isEmpty {
            return resolveTexturePath(asset)
        }
        if let product = overlay["product_ref"] as? [String: Any],
           let url = product["image_url"] as? String, !url.isEmpty {
            return url
        }
        if let url = overlay["image_url"] as? String, !url.isEmpty {
            return url
        }
        return nil
    }

    /// Prefer http(s) URLs; map relative room_scans paths to on-device files.
    private func resolveTexturePath(_ path: String) -> String {
        if path.hasPrefix("http://") || path.hasPrefix("https://") || path.hasPrefix("file://") {
            return path
        }
        return RoomScanPaths.fileURL(relativePath: path).absoluteString
    }

    private func textureForOverlay(_ overlay: [String: Any]?) -> TextureResource? {
        guard let url = imageUrlForOverlay(overlay) else { return nil }
        return textureCache[url]
    }

    private func preloadOverlayTextures() {
        let overlays = activeOverlays()
        for overlay in overlays {
            guard let url = imageUrlForOverlay(overlay), textureCache[url] == nil else { continue }
            loadTexture(from: url) { [weak self] _ in
                guard let self, let arView = self.arView else { return }
                DispatchQueue.main.async {
                    arView.scene.anchors.removeAll()
                    self.addWallAnchorsWithoutPreload(to: arView)
                }
            }
        }
    }

    private func addWallAnchorsWithoutPreload(to arView: ARView) {
        let anchor = AnchorEntity(world: .zero)
        for (index, surface) in surfaces.enumerated() where (surface["category"] as? String) == "wall" {
            let dims = surface["dimensions"] as? [String: Double] ?? [:]
            let width = Float(dims["width"] ?? 1)
            let height = Float(dims["height"] ?? 2.4)
            let mesh = MeshResource.generatePlane(width: width, height: height)
            let overlay = overlayForSurface(surface["id"] as? String)
            let material = materialForOverlay(overlay ?? [:], texture: textureForOverlay(overlay))
            let entity = ModelEntity(mesh: mesh, materials: [material])
            entity.position = SIMD3<Float>(Float(index) * 1.05 - 1.0, 0, -1.8)
            anchor.addChild(entity)
        }
        arView.scene.addAnchor(anchor)
    }

    private func loadTexture(from urlString: String, completion: @escaping (TextureResource?) -> Void) {
        if let cached = textureCache[urlString] {
            completion(cached)
            return
        }
        guard let url = URL(string: urlString) else {
            completion(nil)
            return
        }
        let finish: (Data?) -> Void = { [weak self] data in
            guard let self,
                  let data = data,
                  let image = UIImage(data: data),
                  let cgImage = image.cgImage else {
                DispatchQueue.main.async { completion(nil) }
                return
            }
            do {
                let texture = try TextureResource.generate(from: cgImage, options: .init(semantic: .color))
                DispatchQueue.main.async {
                    self.textureCache[urlString] = texture
                    completion(texture)
                }
            } catch {
                DispatchQueue.main.async { completion(nil) }
            }
        }
        if url.isFileURL {
            DispatchQueue.global(qos: .userInitiated).async {
                finish(try? Data(contentsOf: url))
            }
            return
        }
        URLSession.shared.dataTask(with: url) { data, _, _ in
            finish(data)
        }.resume()
    }

    private func activeOverlays() -> [[String: Any]] {
        if let version = redesign["schema_version"] as? String, version == "2.0",
           let activeId = redesign["active_revision_id"] as? String,
           let revisions = redesign["revisions"] as? [[String: Any]] {
            if let rev = revisions.first(where: { ($0["id"] as? String) == activeId }) {
                return rev["overlays"] as? [[String: Any]] ?? []
            }
        }
        return redesign["overlays"] as? [[String: Any]] ?? []
    }

    private func overlayForSurface(_ surfaceId: String?) -> [String: Any]? {
        let overlays = activeOverlays()
        guard !overlays.isEmpty else { return nil }

        func isNullSurface(_ value: Any?) -> Bool {
            if value == nil { return true }
            if value is NSNull { return true }
            if let s = value as? String { return s.isEmpty }
            return false
        }

        if let surfaceId {
            if let exact = overlays.last(where: { ($0["surface_id"] as? String) == surfaceId }) {
                return exact
            }
        }
        // Design-intent often returns surface_id: null — apply to every wall.
        if let roomWide = overlays.last(where: { isNullSurface($0["surface_id"]) }) {
            return roomWide
        }
        return overlays.last
    }

    private func materialForOverlay(_ overlay: [String: Any], texture: TextureResource? = nil) -> Material {
        if let texture {
            var material = UnlitMaterial()
            material.color = .init(tint: .white.withAlphaComponent(0.92), texture: .init(texture))
            return material
        }
        let hex = overlay["color_hex"] as? String ?? "#FFFFFF"
        return SimpleMaterial(
            color: (UIColor(hex: hex) ?? .white).withAlphaComponent(0.75),
            isMetallic: overlay["type"] as? String == "appliance"
        )
    }

    func applyMaterial(
        surfaceId: String?,
        materialId: String,
        colorHex: String?,
        type: String,
        imageUrl: String? = nil,
        assetUrl: String? = nil,
        productRef: [String: Any]? = nil
    ) -> [String: Any] {
        var overlay: [String: Any] = [
            "surface_id": surfaceId as Any,
            "type": type,
            "material_id": materialId,
            "color_hex": colorHex as Any,
            "asset_url": assetUrl as Any,
        ]
        if let productRef {
            overlay["product_ref"] = productRef
        }
        if let imageUrl {
            overlay["image_url"] = imageUrl
        }

        if let version = redesign["schema_version"] as? String, version == "2.0",
           let activeId = redesign["active_revision_id"] as? String,
           var revisions = redesign["revisions"] as? [[String: Any]] {
            if let idx = revisions.firstIndex(where: { ($0["id"] as? String) == activeId }) {
                var rev = revisions[idx]
                var overlays = rev["overlays"] as? [[String: Any]] ?? []
                overlays.append(overlay)
                rev["overlays"] = overlays
                revisions[idx] = rev
                redesign["revisions"] = revisions
            }
        } else {
            var overlays = redesign["overlays"] as? [[String: Any]] ?? []
            overlays.append(overlay)
            redesign["overlays"] = overlays
        }
        redesign["updated_at"] = ISO8601DateFormatter().string(from: Date())

        let path = RoomScanPaths.redesignPath(projectId: projectId, structureId: structureId, roomId: roomId)
        try? RoomScanJSON.write(path: path, object: redesign)
        if let arView {
            let refresh = { [weak self] in
                guard let self else { return }
                arView.scene.anchors.removeAll()
                self.addWallAnchors(to: arView)
            }
            if Thread.isMainThread {
                refresh()
            } else {
                DispatchQueue.main.async(execute: refresh)
            }
        }
        return overlay
    }

    @objc private func closeTapped() {
        viewController?.dismiss(animated: true)
    }

    @objc private func dictateTapped() {
        dictateButton?.isEnabled = false
        dictateButton?.setTitle("Listening...", for: .normal)
        
        SpeechCapture.requestAuthorization { [weak self] granted in
            guard let self = self else { return }
            guard granted else {
                DispatchQueue.main.async {
                    self.showError("Speech authorization denied.")
                    self.resetDictateButton()
                }
                return
            }
            
            guard let vc = self.viewController else { return }
            SpeechCapture.recognize(from: vc) { [weak self] result in
                guard let self = self else { return }
                DispatchQueue.main.async {
                    self.resetDictateButton()
                    switch result {
                    case .success(let transcript):
                        self.handleDictationResult(transcript)
                    case .failure(let error):
                        self.showError(error.localizedDescription)
                    }
                }
            }
        }
    }
    
    private func resetDictateButton() {
        dictateButton?.isEnabled = true
        dictateButton?.setTitle("Dictate Command", for: .normal)
    }
    
    private func showError(_ message: String) {
        let alert = UIAlertController(title: "Speech Recognition", message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        viewController?.present(alert, animated: true)
    }
    
    private func handleDictationResult(_ transcript: String) {
        guard let plugin = self.plugin else { return }
        plugin.notifyListeners("onARSpeechCommand", data: [
            "projectId": projectId,
            "structureId": structureId,
            "roomId": roomId,
            "transcript": transcript
        ])
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
