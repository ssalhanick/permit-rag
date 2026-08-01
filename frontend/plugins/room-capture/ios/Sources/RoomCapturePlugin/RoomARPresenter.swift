import Foundation
import UIKit
import Capacitor
import Speech

#if canImport(RoomPlan)
import RoomPlan
import RealityKit
import ARKit

/// Room-scoped AR design viewer with surface list and material overlays.
final class RoomARPresenter: NSObject, UITableViewDelegate, UITableViewDataSource, ARSessionDelegate {
    private let call: CAPPluginCall?
    private let projectId: String
    private let structureId: String
    private let roomId: String
    private let roomLabel: String
    private var capture: [String: Any] = [:]
    private var redesign: [String: Any] = [:]
    private var surfaces: [[String: Any]] = []
    private var objects: [[String: Any]] = []
    private var arView: ARView?
    private var viewController: UIViewController?
    private var textureCache: [String: TextureResource] = [:]
    private weak var plugin: RoomCapturePlugin?
    private var dictateButton: UIButton?
    private var selectedSurfaceId: String? = nil
    private var pointedSurfaceId: String? = nil
    private var raycastTimer: Timer? = nil
    private var hudLabel: UILabel? = nil
    private var nudgeStack: UIStackView? = nil
    private var overlayOpacity: Float = 0.3
    private var overlayImageView: UIImageView? = nil
    private var onFinished: (() -> Void)?

    private enum PlacementState {
        case placing
        case locked
    }
    private var placementState: PlacementState = .placing
    private var placementPreviewAnchor: AnchorEntity?
    private var latestPlacementTransform: simd_float4x4?
    private var roomAnchor: AnchorEntity?
    private var lockAnchorButton: UIButton?
    private var repositionButton: UIButton?

    init(
        call: CAPPluginCall? = nil,
        plugin: RoomCapturePlugin? = nil,
        projectId: String,
        structureId: String,
        roomId: String,
        roomLabel: String,
        initialSelectedSurfaceId: String? = nil,
        onFinished: (() -> Void)? = nil
    ) {
        self.call = call
        self.plugin = plugin
        self.projectId = projectId
        self.structureId = structureId
        self.roomId = roomId
        self.roomLabel = roomLabel
        self.selectedSurfaceId = initialSelectedSurfaceId
        self.onFinished = onFinished
        super.init()
    }

    func present(from host: UIViewController) {
        if !Thread.isMainThread {
            DispatchQueue.main.async { [weak self] in
                self?.present(from: host)
            }
            return
        }

        print("[RoomAR] --- START DIRECTORY DEBUG LIST ---")
        debugListDirectory(url: RoomScanPaths.dataDirectory())
        print("[RoomAR] --- END DIRECTORY DEBUG LIST ---")

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
        objects = capture["objects"] as? [[String: Any]] ?? []

        let vc = UIViewController()
        vc.modalPresentationStyle = .fullScreen
        vc.view.backgroundColor = .black

        let arView = ARView(frame: .zero)
        arView.translatesAutoresizingMaskIntoConstraints = false
        arView.automaticallyConfigureSession = false
        vc.view.addSubview(arView)
        self.arView = arView

        // Explicit config (rather than automaticallyConfigureSession) so we can turn on
        // horizontal plane detection — placement raycasts need real plane data to hit.
        let sessionConfig = ARWorldTrackingConfiguration()
        sessionConfig.planeDetection = [.horizontal]
        arView.session.delegate = self
        arView.session.run(sessionConfig)

        let overlayImageView = UIImageView()
        overlayImageView.translatesAutoresizingMaskIntoConstraints = false
        overlayImageView.contentMode = .scaleAspectFill
        overlayImageView.clipsToBounds = true
        overlayImageView.alpha = CGFloat(overlayOpacity)
        vc.view.insertSubview(overlayImageView, aboveSubview: arView)
        self.overlayImageView = overlayImageView

        let previewPath = "room_scans/\(projectId)/\(structureId)/rooms/\(roomId)/generated_preview.png"
        let previewURL = RoomScanPaths.fileURL(relativePath: previewPath)
        if FileManager.default.fileExists(atPath: previewURL.path) {
            if let img = UIImage(contentsOfFile: previewURL.path) {
                overlayImageView.image = img
                print("[RoomAR] Loaded full-screen preview overlay image: \(previewURL.path)")
            }
        }

        let hud = UILabel()
        hud.translatesAutoresizingMaskIntoConstraints = false
        hud.textColor = .green
        hud.backgroundColor = UIColor.black.withAlphaComponent(0.65)
        hud.font = UIFont.systemFont(ofSize: 11, weight: .bold)
        hud.numberOfLines = 0
        hud.layer.cornerRadius = 6
        hud.layer.masksToBounds = true
        vc.view.addSubview(hud)
        self.hudLabel = hud

        let reposition = UIButton(type: .system)
        reposition.setTitle("Reposition", for: .normal)
        reposition.setTitleColor(.white, for: .normal)
        reposition.titleLabel?.font = UIFont.systemFont(ofSize: 11, weight: .semibold)
        reposition.backgroundColor = UIColor.black.withAlphaComponent(0.55)
        reposition.layer.cornerRadius = 6
        reposition.translatesAutoresizingMaskIntoConstraints = false
        reposition.addTarget(self, action: #selector(repositionTapped), for: .touchUpInside)
        reposition.isHidden = true
        vc.view.insertSubview(reposition, aboveSubview: arView)
        self.repositionButton = reposition

        let tapGesture = UITapGestureRecognizer(target: self, action: #selector(handleARViewTap(_:)))
        arView.addGestureRecognizer(tapGesture)

        let longPress = UILongPressGestureRecognizer(target: self, action: #selector(handleARViewLongPress(_:)))
        longPress.minimumPressDuration = 0.5
        arView.addGestureRecognizer(longPress)

        let controlPanel = UIView()
        controlPanel.translatesAutoresizingMaskIntoConstraints = false
        controlPanel.backgroundColor = UIColor.black.withAlphaComponent(0.85)
        vc.view.addSubview(controlPanel)

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
        controlPanel.addSubview(close)

        let dictate = UIButton(type: .system)
        dictate.setTitle("Dictate Command", for: .normal)
        dictate.tintColor = .systemBlue
        dictate.translatesAutoresizingMaskIntoConstraints = false
        dictate.addTarget(self, action: #selector(dictateTapped), for: .touchUpInside)
        controlPanel.addSubview(dictate)
        self.dictateButton = dictate

        let nudge = UIStackView()
        nudge.axis = .horizontal
        nudge.distribution = .fillEqually
        nudge.spacing = 4
        nudge.translatesAutoresizingMaskIntoConstraints = false
        controlPanel.addSubview(nudge)
        self.nudgeStack = nudge

        let titles = ["X-", "X+", "Y-", "Y+", "W-", "W+", "H-", "H+", "O-", "O+"]
        for (index, title) in titles.enumerated() {
            let btn = UIButton(type: .system)
            btn.setTitle(title, for: .normal)
            btn.titleLabel?.font = UIFont.systemFont(ofSize: 10, weight: .bold)
            btn.backgroundColor = UIColor.systemGray6.withAlphaComponent(0.8)
            btn.layer.cornerRadius = 4
            btn.tag = index
            btn.addTarget(self, action: #selector(nudgeTapped(_:)), for: .touchUpInside)
            nudge.addArrangedSubview(btn)
        }

        let lockAnchor = UIButton(type: .system)
        lockAnchor.setTitle("Lock Anchor", for: .normal)
        lockAnchor.setTitleColor(.white, for: .normal)
        lockAnchor.titleLabel?.font = UIFont.systemFont(ofSize: 13, weight: .bold)
        lockAnchor.backgroundColor = UIColor.systemBlue.withAlphaComponent(0.85)
        lockAnchor.layer.cornerRadius = 8
        lockAnchor.translatesAutoresizingMaskIntoConstraints = false
        lockAnchor.addTarget(self, action: #selector(lockAnchorTapped), for: .touchUpInside)
        lockAnchor.isEnabled = false
        controlPanel.addSubview(lockAnchor)
        self.lockAnchorButton = lockAnchor

        NSLayoutConstraint.activate([
            arView.topAnchor.constraint(equalTo: vc.view.topAnchor),
            arView.leadingAnchor.constraint(equalTo: vc.view.leadingAnchor),
            arView.trailingAnchor.constraint(equalTo: vc.view.trailingAnchor),
            arView.heightAnchor.constraint(equalTo: vc.view.heightAnchor, multiplier: 0.55),
            
            overlayImageView.topAnchor.constraint(equalTo: arView.topAnchor),
            overlayImageView.leadingAnchor.constraint(equalTo: arView.leadingAnchor),
            overlayImageView.trailingAnchor.constraint(equalTo: arView.trailingAnchor),
            overlayImageView.bottomAnchor.constraint(equalTo: arView.bottomAnchor),
            
            hud.topAnchor.constraint(equalTo: arView.topAnchor, constant: 12),
            hud.leadingAnchor.constraint(equalTo: arView.leadingAnchor, constant: 12),
            hud.trailingAnchor.constraint(equalTo: arView.trailingAnchor, constant: -12),
            
            table.topAnchor.constraint(equalTo: arView.bottomAnchor),
            table.leadingAnchor.constraint(equalTo: vc.view.leadingAnchor),
            table.trailingAnchor.constraint(equalTo: vc.view.trailingAnchor),
            table.bottomAnchor.constraint(equalTo: controlPanel.topAnchor),
            
            controlPanel.leadingAnchor.constraint(equalTo: vc.view.leadingAnchor),
            controlPanel.trailingAnchor.constraint(equalTo: vc.view.trailingAnchor),
            controlPanel.bottomAnchor.constraint(equalTo: vc.view.bottomAnchor),
            controlPanel.topAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.bottomAnchor, constant: -110),
            
            nudge.topAnchor.constraint(equalTo: controlPanel.topAnchor, constant: 10),
            nudge.leadingAnchor.constraint(equalTo: controlPanel.leadingAnchor, constant: 12),
            nudge.trailingAnchor.constraint(equalTo: controlPanel.trailingAnchor, constant: -12),
            nudge.heightAnchor.constraint(equalToConstant: 32),
            
            close.topAnchor.constraint(equalTo: nudge.bottomAnchor, constant: 12),
            close.leadingAnchor.constraint(equalTo: controlPanel.leadingAnchor, constant: 20),
            close.heightAnchor.constraint(equalToConstant: 44),
            
            dictate.topAnchor.constraint(equalTo: nudge.bottomAnchor, constant: 12),
            dictate.trailingAnchor.constraint(equalTo: controlPanel.trailingAnchor, constant: -20),
            dictate.heightAnchor.constraint(equalToConstant: 44),

            lockAnchor.topAnchor.constraint(equalTo: controlPanel.topAnchor, constant: 10),
            lockAnchor.leadingAnchor.constraint(equalTo: controlPanel.leadingAnchor, constant: 12),
            lockAnchor.trailingAnchor.constraint(equalTo: controlPanel.trailingAnchor, constant: -12),
            lockAnchor.heightAnchor.constraint(equalToConstant: 32),

            reposition.topAnchor.constraint(equalTo: hud.bottomAnchor, constant: 8),
            reposition.trailingAnchor.constraint(equalTo: arView.trailingAnchor, constant: -12),
            reposition.widthAnchor.constraint(equalToConstant: 100),
            reposition.heightAnchor.constraint(equalToConstant: 30),
        ])

        enterPlacementMode()
        updateDictateButtonTitle()

        self.raycastTimer = Timer.scheduledTimer(withTimeInterval: 0.3, repeats: true) { [weak self] _ in
            guard let self else { return }
            switch self.placementState {
            case .placing:
                self.updatePlacementPreview()
            case .locked:
                self.performCenterRaycast()
            }
        }

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

    // MARK: - Guided placement (aim, preview, lock)
    //
    // The AR session here has no shared world map with the original RoomPlan
    // scan, so nothing can align this diorama with the room's actual real
    // walls. What we *can* do is anchor it to a real detected surface near
    // the user, deliberately, instead of a fixed offset from wherever
    // tracking happened to start. Placement is a distinct phase — nothing is
    // built until the user aims and taps "Lock Anchor" — rather than an
    // automatic first-plane guess the user has no control over.

    func session(_ session: ARSession, cameraDidChangeTrackingState camera: ARCamera) {
        DispatchQueue.main.async { [weak self] in
            self?.handleTrackingState(camera.trackingState)
        }
    }

    private func handleTrackingState(_ state: ARCamera.TrackingState) {
        guard placementState == .placing else { return }
        switch state {
        case .limited(let reason):
            let hint: String
            switch reason {
            case .initializing: hint = "Move your phone slowly to start tracking…"
            case .excessiveMotion: hint = "Move more slowly."
            case .insufficientFeatures: hint = "Point at a well-lit surface with detail."
            case .relocalizing: hint = "Finding your position…"
            @unknown default: hint = "Move your phone slowly."
            }
            hudLabel?.text = " \(hint)"
        case .normal:
            hudLabel?.text = " Point at the floor where the room should sit, then tap Lock Anchor"
        case .notAvailable:
            hudLabel?.text = " Tracking unavailable."
        }
    }

    private func enterPlacementMode() {
        placementState = .placing
        nudgeStack?.isHidden = true
        dictateButton?.isHidden = true
        lockAnchorButton?.isHidden = false
        lockAnchorButton?.isEnabled = false
        repositionButton?.isHidden = true
        hudLabel?.text = " Point at the floor where the room should sit, then tap Lock Anchor"
    }

    private func enterLockedMode() {
        placementState = .locked
        nudgeStack?.isHidden = false
        dictateButton?.isHidden = false
        lockAnchorButton?.isHidden = true
        repositionButton?.isHidden = false
    }

    private func updatePlacementPreview() {
        guard let arView = arView else { return }
        let center = CGPoint(x: arView.bounds.midX, y: arView.bounds.midY)
        let results = arView.raycast(from: center, allowing: .estimatedPlane, alignment: .horizontal)
        guard let hit = results.first else {
            latestPlacementTransform = nil
            lockAnchorButton?.isEnabled = false
            return
        }
        latestPlacementTransform = hit.worldTransform
        lockAnchorButton?.isEnabled = true
        updatePlacementPreviewEntity(worldTransform: hit.worldTransform)
    }

    private func updatePlacementPreviewEntity(worldTransform: simd_float4x4) {
        guard let arView = arView else { return }
        if let existing = placementPreviewAnchor {
            arView.scene.removeAnchor(existing)
        }
        let anchor = AnchorEntity(world: worldTransform)
        anchor.addChild(buildPlacementFootprintEntity())
        arView.scene.addAnchor(anchor)
        placementPreviewAnchor = anchor
    }

    private func estimatedFootprintSize() -> SIMD2<Float> {
        var minX: Float = .greatestFiniteMagnitude, maxX: Float = -.greatestFiniteMagnitude
        var minZ: Float = .greatestFiniteMagnitude, maxZ: Float = -.greatestFiniteMagnitude
        var found = false
        for surface in surfaces where (surface["category"] as? String) == "wall" {
            guard let matrixArray = surface["transform_matrix"] as? [Double],
                  let matrix = transformMatrix(from: matrixArray) else { continue }
            let pos = matrix.columns.3
            minX = min(minX, pos.x); maxX = max(maxX, pos.x)
            minZ = min(minZ, pos.z); maxZ = max(maxZ, pos.z)
            found = true
        }
        guard found else { return SIMD2<Float>(2, 2) }
        return SIMD2<Float>(max(maxX - minX, 1.0), max(maxZ - minZ, 1.0))
    }

    private func buildPlacementFootprintEntity() -> Entity {
        let size = estimatedFootprintSize()
        let mesh = MeshResource.generateBox(width: size.x, height: 0.02, depth: size.y)
        var material = UnlitMaterial()
        material.color = .init(tint: UIColor.systemBlue.withAlphaComponent(0.35))
        return ModelEntity(mesh: mesh, materials: [material])
    }

    @objc private func lockAnchorTapped() {
        guard let transform = latestPlacementTransform, let arView = arView else { return }
        if let previewAnchor = placementPreviewAnchor {
            arView.scene.removeAnchor(previewAnchor)
            placementPreviewAnchor = nil
        }
        lockRoomAnchor(worldTransform: transform)
    }

    @objc private func repositionTapped() {
        if let anchor = roomAnchor {
            arView?.scene.removeAnchor(anchor)
        }
        roomAnchor = nil
        selectedSurfaceId = nil
        pointedSurfaceId = nil
        enterPlacementMode()
    }

    /// Floor height in the captured room's own coordinate frame, so the
    /// captured floor lands on the real detected plane rather than floating
    /// at an arbitrary height. Falls back to an estimate from wall geometry
    /// when no floor surface was captured (pre-iOS 17 scans) — worth
    /// confirming visually on-device, this fallback is a reasonable guess,
    /// not measured.
    private func estimatedFloorY() -> Float {
        if let floorSurface = surfaces.first(where: { ($0["category"] as? String) == "floor" }),
           let matrixArray = floorSurface["transform_matrix"] as? [Double],
           let matrix = transformMatrix(from: matrixArray) {
            return matrix.columns.3.y
        }
        return calculateCentroid().y - 1.2
    }

    private func lockRoomAnchor(worldTransform: simd_float4x4) {
        guard let arView = arView else { return }
        if let existing = roomAnchor {
            arView.scene.removeAnchor(existing)
        }
        let centroid = calculateCentroid()
        let floorY = estimatedFloorY()
        let anchor = AnchorEntity(world: worldTransform)
        anchor.position -= SIMD3<Float>(centroid.x, floorY, centroid.z)
        populateRoomEntities(in: anchor)
        arView.scene.addAnchor(anchor)
        roomAnchor = anchor
        enterLockedMode()
    }

    private func populateRoomEntities(in anchor: AnchorEntity) {
        var wallCount = 0
        var doorCount = 0
        var windowCount = 0
        var openingCount = 0
        var floorCount = 0

        for (index, surface) in surfaces.enumerated() {
            let cat = surface["category"] as? String ?? ""
            guard cat == "wall" || cat == "door" || cat == "window" || cat == "opening" || cat == "floor" else { continue }

            if cat == "wall" { wallCount += 1 }
            else if cat == "door" { doorCount += 1 }
            else if cat == "window" { windowCount += 1 }
            else if cat == "opening" { openingCount += 1 }
            else if cat == "floor" { floorCount += 1 }

            let entity = buildWallEntity(surface: surface, index: index)
            anchor.addChild(entity)
        }

        for (index, object) in objects.enumerated() {
            anchor.addChild(buildObjectEntity(object: object, index: index))
        }

        var summary = " Scan Loaded: \(surfaces.count) surfaces\n - Walls: \(wallCount) | Doors: \(doorCount)\n - Windows: \(windowCount) | Openings: \(openingCount) | Floors: \(floorCount)"
        if !objects.isEmpty {
            summary += "\n - Detected items: \(objects.count)"
        }
        hudLabel?.text = summary

        preloadOverlayTextures()
    }

    /// Detected fixtures/appliances (sinks, refrigerators, etc.) — read-only:
    /// no collision shapes, not addressable by surfaceId, so they never enter
    /// the tap-to-select/paint-picker/nudge flow that surfaces use.
    private func buildObjectEntity(object: [String: Any], index: Int) -> Entity {
        let dims = object["dimensions"] as? [String: Double] ?? [:]
        let width = Float(dims["width"] ?? 0.3)
        let height = Float(dims["height"] ?? 0.3)
        let depth = Float(dims["depth"] ?? 0.3)
        let objectId = object["id"] as? String ?? "object_\(index)"

        let parent = Entity()
        parent.name = objectId

        let mesh = MeshResource.generateBox(width: width, height: height, depth: depth)
        var material = UnlitMaterial()
        material.color = .init(tint: UIColor.systemOrange.withAlphaComponent(0.45))
        let child = ModelEntity(mesh: mesh, materials: [material])
        child.name = objectId
        parent.addChild(child)

        if let matrixArray = object["transform_matrix"] as? [Double],
           let matrix = transformMatrix(from: matrixArray) {
            parent.transform.matrix = matrix
        }

        return parent
    }

    /// Reconciles existing entities against current surfaces/overlays in
    /// place (update materials/geometry, add/remove segments as needed)
    /// instead of tearing down and rebuilding the whole scene — a full
    /// rebuild on every material tap or nudge was the other half of what
    /// made the AR view feel unstable, independent of placement itself.
    private func syncWallEntities() {
        guard let anchor = roomAnchor else { return }
        for (index, surface) in surfaces.enumerated() {
            let cat = surface["category"] as? String ?? ""
            guard cat == "wall" || cat == "door" || cat == "window" || cat == "opening" || cat == "floor" else { continue }
            let surfaceId = surface["id"] as? String
            let name = surfaceId ?? "\(cat)_\(index)"
            guard let parent = anchor.children.first(where: { $0.name == name }) else {
                anchor.addChild(buildWallEntity(surface: surface, index: index))
                continue
            }

            let isSelected = (selectedSurfaceId != nil && selectedSurfaceId == surfaceId)
            let isPointed = (selectedSurfaceId == nil && pointedSurfaceId != nil && pointedSurfaceId == surfaceId)
            let specs = wallSegmentSpecs(surface: surface, surfaceId: surfaceId, isSelected: isSelected, isPointed: isPointed)
            let existingChildren = parent.children.compactMap { $0 as? ModelEntity }

            for (i, spec) in specs.enumerated() {
                if i < existingChildren.count {
                    let child = existingChildren[i]
                    child.model?.mesh = spec.mesh
                    child.model?.materials = [spec.material]
                    child.position = spec.localPosition
                    child.generateCollisionShapes(recursive: true)
                } else {
                    let child = ModelEntity(mesh: spec.mesh, materials: [spec.material])
                    child.name = parent.name
                    child.position = spec.localPosition
                    child.generateCollisionShapes(recursive: true)
                    parent.addChild(child)
                }
            }
            if existingChildren.count > specs.count {
                for extra in existingChildren[specs.count...] {
                    extra.removeFromParent()
                }
            }
        }
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
                    self.updateWallMaterials()
                }
            }
        }
    }

    private func updateWallMaterials() {
        guard let arView = arView else { return }
        for anchor in arView.scene.anchors {
            for parentEntity in anchor.children {
                let surfaceId = parentEntity.name
                guard !surfaceId.isEmpty else { continue }
                
                guard let surface = surfaces.first(where: { ($0["id"] as? String) == surfaceId }) else { continue }
                let category = surface["category"] as? String ?? "wall"
                let isSelected = (selectedSurfaceId != nil && selectedSurfaceId == surfaceId)
                let isPointed = (selectedSurfaceId == nil && pointedSurfaceId != nil && pointedSurfaceId == surfaceId)
                
                let overlays = activeOverlays().filter { ($0["surface_id"] as? String) == surfaceId }
                
                for (idx, subEntity) in parentEntity.children.enumerated() {
                    guard let modelEntity = subEntity as? ModelEntity else { continue }
                    
                    let material: Material
                    if category == "door" {
                        var unlit = UnlitMaterial()
                        unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.65) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : (UIColor(hex: "#8B5A2B")?.withAlphaComponent(0.4) ?? .brown.withAlphaComponent(0.4))))
                        material = unlit
                    } else if category == "window" {
                        var unlit = UnlitMaterial()
                        unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.65) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : (UIColor(hex: "#ADD8E6")?.withAlphaComponent(0.3) ?? .blue.withAlphaComponent(0.3))))
                        material = unlit
                    } else if category == "opening" {
                        var unlit = UnlitMaterial()
                        unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.65) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : UIColor.lightGray.withAlphaComponent(0.15)))
                        material = unlit
                    } else if category == "floor" {
                        var unlit = UnlitMaterial()
                        unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.65) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : (UIColor(hex: "#C2A878")?.withAlphaComponent(0.35) ?? .gray.withAlphaComponent(0.35))))
                        material = unlit
                    } else {
                        // Wall
                        if overlays.isEmpty {
                            let overlay = overlayForSurface(surfaceId)
                            if let overlay {
                                material = materialForOverlay(overlay, texture: textureForOverlay(overlay), isSelected: isSelected, isPointed: isPointed)
                            } else {
                                var unlit = UnlitMaterial()
                                unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.6) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : UIColor.white.withAlphaComponent(0.2)))
                                material = unlit
                            }
                        } else if idx < overlays.count {
                            let overlay = overlays[idx]
                            material = materialForOverlay(overlay, texture: textureForOverlay(overlay), isSelected: isSelected, isPointed: isPointed)
                        } else {
                            var unlit = UnlitMaterial()
                            unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.6) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : UIColor.white.withAlphaComponent(0.2)))
                            material = unlit
                        }
                    }
                    modelEntity.model?.materials = [material]
                }
            }
        }
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
            guard let self = self else { return }
            guard let data = data else {
                print("[RoomAR] finish: Data was nil for url: \(urlString)")
                DispatchQueue.main.async { completion(nil) }
                return
            }
            guard let image = UIImage(data: data) else {
                print("[RoomAR] finish: Failed to parse UIImage from data (size: \(data.count) bytes) for url: \(urlString)")
                DispatchQueue.main.async { completion(nil) }
                return
            }
            guard let cgImage = image.cgImage else {
                print("[RoomAR] finish: Failed to get cgImage from UIImage for url: \(urlString)")
                DispatchQueue.main.async { completion(nil) }
                return
            }
            do {
                let texture = try TextureResource.generate(from: cgImage, options: .init(semantic: .color))
                print("[RoomAR] finish: Successfully generated TextureResource for url: \(urlString)")
                DispatchQueue.main.async {
                    self.textureCache[urlString] = texture
                    completion(texture)
                }
            } catch {
                print("[RoomAR] finish: TextureResource.generate failed: \(error.localizedDescription) for url: \(urlString)")
                DispatchQueue.main.async { completion(nil) }
            }
        }

        if url.isFileURL {
            DispatchQueue.global(qos: .userInitiated).async {
                let data = try? Data(contentsOf: url)
                if data == nil {
                    print("[RoomAR] Failed to load local file: \(url.path)")
                } else {
                    print("[RoomAR] Loaded local file: \(url.path) (size: \(data?.count ?? 0) bytes)")
                }
                finish(data)
            }
            return
        }

        print("[RoomAR] Loading remote texture: \(urlString)")
        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                print("[RoomAR] Remote texture task failed: \(error.localizedDescription)")
            }
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
        return nil
    }

    private func materialForOverlay(_ overlay: [String: Any], texture: TextureResource? = nil, isSelected: Bool = false, isPointed: Bool = false) -> Material {
        if isSelected {
            var material = UnlitMaterial()
            material.color = .init(tint: UIColor.systemBlue.withAlphaComponent(0.65))
            return material
        }
        if isPointed {
            var material = UnlitMaterial()
            material.color = .init(tint: UIColor.systemGreen.withAlphaComponent(0.35))
            return material
        }
        if let texture {
            var material = UnlitMaterial()
            material.color = .init(tint: .white.withAlphaComponent(CGFloat(overlayOpacity)), texture: .init(texture))
            return material
        }
        let hex = overlay["color_hex"] as? String ?? "#FFFFFF"
        var material = UnlitMaterial()
        material.color = .init(tint: (UIColor(hex: hex) ?? .white).withAlphaComponent(CGFloat(overlayOpacity)))
        return material
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
        if roomAnchor != nil {
            let refresh = { [weak self] in
                guard let self else { return }
                self.syncWallEntities()
            }
            if Thread.isMainThread {
                refresh()
            } else {
                DispatchQueue.main.async(execute: refresh)
            }
        }
        return overlay
    }

    /// Tear down the ARKit session and release the scene.
    ///
    /// Without the session pause the camera keeps running after dismissal, and
    /// without dropping the view and texture cache every AR session stays
    /// resident for the life of the app. onFinished lets the plugin release its
    /// own reference, matching RoomCapturePresenter and StructureCapturePresenter.
    @objc private func closeTapped() {
        raycastTimer?.invalidate()
        raycastTimer = nil

        arView?.session.pause()
        arView?.scene.anchors.removeAll()
        arView?.removeFromSuperview()
        arView = nil
        textureCache.removeAll()

        let vc = viewController
        viewController = nil
        let finish = onFinished
        onFinished = nil
        vc?.dismiss(animated: true) {
            finish?()
        }
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
        updateDictateButtonTitle()
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
            "transcript": transcript,
            "selectedSurfaceId": selectedSurfaceId ?? pointedSurfaceId ?? ""
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
        if let surfaceId = surfaces[indexPath.row]["id"] as? String {
            selectedSurfaceId = surfaceId
            updateWallMaterials()
            updateDictateButtonTitle()
            showMaterialPicker(for: surfaceId)
        }
    }

    private func debugListDirectory(url: URL, depth: Int = 0) {
        let indent = String(repeating: "  ", count: depth)
        guard let entries = try? FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: nil) else {
            print("[RoomAR] debugList: Cannot read \(url.path)")
            return
        }
        print("[RoomAR] debugList:\(indent)Dir: \(url.lastPathComponent)")
        for entry in entries {
            let isDir = (try? entry.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            if isDir {
                debugListDirectory(url: entry, depth: depth + 1)
            } else {
                print("[RoomAR] debugList:\(indent)  - File: \(entry.lastPathComponent)")
            }
        }
    }

    @objc private func handleARViewTap(_ gesture: UITapGestureRecognizer) {
        guard let arView = arView else { return }
        let location = gesture.location(in: arView)
        if let hitEntity = arView.entity(at: location) {
            var current: Entity? = hitEntity
            while let node = current {
                if !node.name.isEmpty && surfaces.contains(where: { ($0["id"] as? String) == node.name }) {
                    if selectedSurfaceId == node.name {
                        selectedSurfaceId = nil
                    } else {
                        selectedSurfaceId = node.name
                    }
                    
                    updateWallMaterials()
                    updateDictateButtonTitle()
                    return
                }
                current = node.parent
            }
        }
    }
    @objc private func handleARViewLongPress(_ gesture: UILongPressGestureRecognizer) {
        guard gesture.state == .began, let arView = arView else { return }
        let location = gesture.location(in: arView)
        if let hitEntity = arView.entity(at: location) {
            var current: Entity? = hitEntity
            while let node = current {
                if !node.name.isEmpty && surfaces.contains(where: { ($0["id"] as? String) == node.name }) {
                    selectedSurfaceId = node.name
                    updateWallMaterials()
                    updateDictateButtonTitle()
                    
                    showGenerativeDialog(for: node.name)
                    return
                }
                current = node.parent
            }
        }
    }

    private func showGenerativeDialog(for surfaceId: String) {
        let alert = UIAlertController(
            title: "Generative Refurbish",
            message: "Enter custom prompt or select a suggested texture below:",
            preferredStyle: .alert
        )
        
        alert.addTextField { textField in
            textField.placeholder = "e.g., green marble, floral wallpaper"
        }
        
        let generateAction = UIAlertAction(title: "Generate", style: .default) { [weak self] _ in
            guard let self = self else { return }
            let prompt = alert.textFields?.first?.text ?? ""
            guard !prompt.isEmpty else { return }
            self.handleCustomPrompt(prompt, surfaceId: surfaceId)
        }
        alert.addAction(generateAction)
        
        for preset in MaterialCatalog.presets {
            let action = UIAlertAction(title: preset.label, style: .default) { [weak self] _ in
                guard let self = self else { return }
                _ = self.applyMaterial(
                    surfaceId: surfaceId,
                    materialId: preset.id,
                    colorHex: preset.colorHex,
                    type: preset.type
                )
            }
            alert.addAction(action)
        }
        
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        viewController?.present(alert, animated: true)
    }

    private func handleCustomPrompt(_ prompt: String, surfaceId: String) {
        guard let plugin = self.plugin else { return }
        plugin.notifyListeners("onARSpeechCommand", data: [
            "projectId": projectId,
            "structureId": structureId,
            "roomId": roomId,
            "transcript": prompt,
            "selectedSurfaceId": surfaceId
        ])
    }

    private func updateDictateButtonTitle() {
        if let _ = selectedSurfaceId {
            dictateButton?.setTitle("Dictate for Selected Wall", for: .normal)
        } else if let _ = pointedSurfaceId {
            dictateButton?.setTitle("Dictate for Pointed Wall", for: .normal)
        } else {
            dictateButton?.setTitle("Dictate Command", for: .normal)
        }
    }

    private func showMaterialPicker(for surfaceId: String) {
        let alert = UIAlertController(title: "Apply material", message: nil, preferredStyle: .actionSheet)
        if let popover = alert.popoverPresentationController {
            popover.sourceView = viewController?.view
            let bounds = viewController?.view.bounds ?? .zero
            popover.sourceRect = CGRect(
                x: bounds.midX,
                y: bounds.midY,
                width: 0,
                height: 0
            )
            popover.permittedArrowDirections = []
        }
        for preset in MaterialCatalog.presets {
            alert.addAction(UIAlertAction(title: preset.label, style: .default) { [weak self] _ in
                guard let self = self else { return }
                _ = self.applyMaterial(
                    surfaceId: surfaceId,
                    materialId: preset.id,
                    colorHex: preset.colorHex,
                    type: preset.type
                )
                self.selectedSurfaceId = nil
                self.updateWallMaterials()
                self.updateDictateButtonTitle()
            })
        }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { [weak self] _ in
            guard let self = self else { return }
            self.selectedSurfaceId = nil
            self.updateWallMaterials()
            self.updateDictateButtonTitle()
        })
        viewController?.present(alert, animated: true)
    }

    /// Builds a flat mesh from RoomPlan's real wall polygon (iOS 17+) instead
    /// of a rectangular box — nil if unavailable (older scan, pre-iOS 17
    /// capture, or too few points), so callers fall back to generateBox.
    /// Emits both triangle windings so the wall renders from either side
    /// regardless of material face-culling defaults.
    private func polygonMesh(from corners: [[String: Any]]?) -> MeshResource? {
        guard let corners, corners.count >= 3 else { return nil }
        let points: [SIMD3<Float>] = corners.map {
            SIMD3<Float>(
                Float($0["x"] as? Double ?? 0),
                Float($0["y"] as? Double ?? 0),
                Float($0["z"] as? Double ?? 0)
            )
        }
        var descriptor = MeshDescriptor(name: "wallPolygon")
        descriptor.positions = MeshBuffers.Positions(points)
        var indices: [UInt32] = []
        for i in 1..<(points.count - 1) {
            indices.append(0)
            indices.append(UInt32(i))
            indices.append(UInt32(i + 1))
            indices.append(0)
            indices.append(UInt32(i + 1))
            indices.append(UInt32(i))
        }
        descriptor.primitives = .triangles(indices)
        return try? MeshResource.generate(from: [descriptor])
    }

    private struct WallSegmentSpec {
        let mesh: MeshResource
        let material: Material
        let localPosition: SIMD3<Float>
    }

    /// Desired child-entity specs for a surface, shared by buildWallEntity
    /// (first build) and syncWallEntities (in-place reconciliation) so both
    /// stay in lockstep instead of drifting apart.
    private func wallSegmentSpecs(
        surface: [String: Any],
        surfaceId: String?,
        isSelected: Bool,
        isPointed: Bool
    ) -> [WallSegmentSpec] {
        let dims = surface["dimensions"] as? [String: Double] ?? [:]
        let width = Float(dims["width"] ?? 1)
        let height = Float(dims["height"] ?? 2.4)
        let depth = Float(dims["depth"] ?? 1)
        let category = surface["category"] as? String ?? "wall"
        let overlays = activeOverlays().filter { ($0["surface_id"] as? String) == surfaceId }

        switch category {
        case "floor":
            // Floor surfaces are flat: RoomPlan reports the second planar extent
            // in the "depth" field rather than a vertical height, so swap axes
            // and use a thin fixed thickness for visibility.
            let mesh = MeshResource.generateBox(width: width, height: 0.02, depth: depth)
            var unlit = UnlitMaterial()
            unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.65) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : (UIColor(hex: "#C2A878")?.withAlphaComponent(0.35) ?? .gray.withAlphaComponent(0.35))))
            return [WallSegmentSpec(mesh: mesh, material: unlit, localPosition: .zero)]
        case "door":
            let mesh = MeshResource.generateBox(width: width, height: height, depth: 0.05)
            var unlit = UnlitMaterial()
            unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.65) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : (UIColor(hex: "#8B5A2B")?.withAlphaComponent(0.4) ?? .brown.withAlphaComponent(0.4))))
            return [WallSegmentSpec(mesh: mesh, material: unlit, localPosition: SIMD3<Float>(0, 0, 0.005))]
        case "window":
            let mesh = MeshResource.generateBox(width: width, height: height, depth: 0.05)
            var unlit = UnlitMaterial()
            unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.65) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : (UIColor(hex: "#ADD8E6")?.withAlphaComponent(0.3) ?? .blue.withAlphaComponent(0.3))))
            return [WallSegmentSpec(mesh: mesh, material: unlit, localPosition: SIMD3<Float>(0, 0, 0.005))]
        case "opening":
            let mesh = MeshResource.generateBox(width: width, height: height, depth: 0.05)
            var unlit = UnlitMaterial()
            unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.65) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : UIColor.lightGray.withAlphaComponent(0.15)))
            return [WallSegmentSpec(mesh: mesh, material: unlit, localPosition: SIMD3<Float>(0, 0, 0.005))]
        default:
            // Wall category
            if overlays.isEmpty {
                let polygon = polygonMesh(from: surface["polygon_corners"] as? [[String: Any]])
                let mesh = polygon ?? MeshResource.generateBox(width: width, height: height, depth: 0.05)
                print("[RoomAR] Wall mesh source for \(surfaceId ?? "?"): \(polygon != nil ? "real polygon" : "box fallback")")
                let material: Material
                if let overlay = overlayForSurface(surfaceId) {
                    material = materialForOverlay(overlay, texture: textureForOverlay(overlay), isSelected: isSelected, isPointed: isPointed)
                } else {
                    var unlit = UnlitMaterial()
                    unlit.color = .init(tint: isSelected ? UIColor.systemBlue.withAlphaComponent(0.6) : (isPointed ? UIColor.systemGreen.withAlphaComponent(0.35) : UIColor.white.withAlphaComponent(0.2)))
                    material = unlit
                }
                return [WallSegmentSpec(mesh: mesh, material: material, localPosition: .zero)]
            }
            return overlays.enumerated().map { idx, overlay in
                let xMin = Float(overlay["x_min"] as? Double ?? 0.0)
                let xMax = Float(overlay["x_max"] as? Double ?? 1.0)
                let yMin = Float(overlay["y_min"] as? Double ?? 0.0)
                let yMax = Float(overlay["y_max"] as? Double ?? 1.0)

                let w = width * (xMax - xMin)
                let h = height * (yMax - yMin)

                let segmentMesh = MeshResource.generateBox(width: w, height: h, depth: 0.05)
                let segmentMat = materialForOverlay(overlay, texture: textureForOverlay(overlay), isSelected: isSelected, isPointed: isPointed)

                let localX = -width / 2.0 + xMin * width + w / 2.0
                let localY = -height / 2.0 + yMin * height + h / 2.0
                let localZ = Float(idx) * 0.005 + 0.001

                return WallSegmentSpec(mesh: segmentMesh, material: segmentMat, localPosition: SIMD3<Float>(localX, localY, localZ))
            }
        }
    }

    private func buildWallEntity(surface: [String: Any], index: Int) -> Entity {
        let surfaceId = surface["id"] as? String
        let category = surface["category"] as? String ?? "wall"

        let parent = Entity()
        parent.name = surfaceId ?? "\(category)_\(index)"

        let isSelected = (selectedSurfaceId != nil && selectedSurfaceId == surfaceId)
        let isPointed = (selectedSurfaceId == nil && pointedSurfaceId != nil && pointedSurfaceId == surfaceId)
        let specs = wallSegmentSpecs(surface: surface, surfaceId: surfaceId, isSelected: isSelected, isPointed: isPointed)

        for spec in specs {
            let child = ModelEntity(mesh: spec.mesh, materials: [spec.material])
            child.name = parent.name
            child.position = spec.localPosition
            child.generateCollisionShapes(recursive: true)
            parent.addChild(child)
        }

        if let matrixArray = surface["transform_matrix"] as? [Double],
           let matrix = transformMatrix(from: matrixArray) {
            parent.transform.matrix = matrix
        } else {
            parent.position = SIMD3<Float>(Float(index) * 1.05 - 1.0, 0, -1.8)
        }

        return parent
    }

    private func transformMatrix(from array: [Double]?) -> simd_float4x4? {
        guard let array = array, array.count == 16 else { return nil }
        var matrix = simd_float4x4()
        matrix.columns.0 = SIMD4<Float>(Float(array[0]), Float(array[1]), Float(array[2]), Float(array[3]))
        matrix.columns.1 = SIMD4<Float>(Float(array[4]), Float(array[5]), Float(array[6]), Float(array[7]))
        matrix.columns.2 = SIMD4<Float>(Float(array[8]), Float(array[9]), Float(array[10]), Float(array[11]))
        matrix.columns.3 = SIMD4<Float>(Float(array[12]), Float(array[13]), Float(array[14]), Float(array[15]))
        return matrix
    }

    private func calculateCentroid() -> SIMD3<Float> {
        var wallPositions: [SIMD3<Float>] = []
        for surface in surfaces where (surface["category"] as? String) == "wall" {
            if let matrixArray = surface["transform_matrix"] as? [Double],
               let matrix = transformMatrix(from: matrixArray) {
                let pos = SIMD3<Float>(matrix.columns.3.x, matrix.columns.3.y, matrix.columns.3.z)
                print("[RoomAR] Wall \(surface["id"] as? String ?? "") position: \(pos)")
                wallPositions.append(pos)
            }
        }
        if !wallPositions.isEmpty {
            let sum = wallPositions.reduce(SIMD3<Float>(0, 0, 0), +)
            let centroid = sum / Float(wallPositions.count)
            print("[RoomAR] Calculated centroid: \(centroid) for \(wallPositions.count) walls")
            return centroid
        }
        print("[RoomAR] Warning: no wall positions found, centroid is zero")
        return SIMD3<Float>(0, 0, 0)
    }

    @objc private func nudgeTapped(_ sender: UIButton) {
        switch sender.tag {
        case 0: updateOverlayValue(xShift: -0.02)
        case 1: updateOverlayValue(xShift: 0.02)
        case 2: updateOverlayValue(yShift: -0.02)
        case 3: updateOverlayValue(yShift: 0.02)
        case 4: updateOverlayValue(wScale: 0.95)
        case 5: updateOverlayValue(wScale: 1.05)
        case 6: updateOverlayValue(hScale: 0.95)
        case 7: updateOverlayValue(hScale: 1.05)
        case 8: updateOpacity(by: -0.1)
        case 9: updateOpacity(by: 0.1)
        default: break
        }
    }

    private func updateOpacity(by delta: Float) {
        overlayOpacity = max(0.0, min(1.0, overlayOpacity + delta))
        
        // Update 2D image alpha
        overlayImageView?.alpha = CGFloat(overlayOpacity)
        
        // Update HUD text
        hudLabel?.text = " Blended Opacity: \(Int(overlayOpacity * 100))%"
        
        // Refresh materials in-place
        updateWallMaterials()
    }

    private func updateOverlayValue(xShift: Float = 0, yShift: Float = 0, wScale: Float = 1, hScale: Float = 1) {
        guard let selectedId = selectedSurfaceId else { return }
        
        var overlays = activeOverlays()
        
        // If selected wall doesn't have an overlay, seed a green alignment paint overlay
        if !overlays.contains(where: { ($0["surface_id"] as? String) == selectedId }) {
            let newOverlay: [String: Any] = [
                "surface_id": selectedId,
                "type": "paint",
                "color_hex": "#00FF00",
                "x_min": 0.25,
                "x_max": 0.75,
                "y_min": 0.25,
                "y_max": 0.75
            ]
            overlays.append(newOverlay)
        }
        
        if let idx = overlays.firstIndex(where: { ($0["surface_id"] as? String) == selectedId }) {
            var overlay = overlays[idx]
            
            var xMin = Float(overlay["x_min"] as? Double ?? 0.0)
            var xMax = Float(overlay["x_max"] as? Double ?? 1.0)
            var yMin = Float(overlay["y_min"] as? Double ?? 0.0)
            var yMax = Float(overlay["y_max"] as? Double ?? 1.0)
            
            xMin += xShift
            xMax += xShift
            yMin += yShift
            yMax += yShift
            
            let cx = (xMin + xMax) / 2.0
            let cy = (yMin + yMax) / 2.0
            let hw = (xMax - xMin) / 2.0 * wScale
            let hh = (yMax - yMin) / 2.0 * hScale
            
            xMin = cx - hw
            xMax = cx + hw
            yMin = cy - hh
            yMax = cy + hh
            
            xMin = max(0.0, min(1.0, xMin))
            xMax = max(0.0, min(1.0, xMax))
            yMin = max(0.0, min(1.0, yMin))
            yMax = max(0.0, min(1.0, yMax))
            
            overlay["x_min"] = Double(xMin)
            overlay["x_max"] = Double(xMax)
            overlay["y_min"] = Double(yMin)
            overlay["y_max"] = Double(yMax)
            
            // Force paint overlay so green alignment box is drawn
            overlay["type"] = "paint"
            overlay["color_hex"] = "#00FF00"
            
            overlays[idx] = overlay
            
            // Write back based on version
            if let version = redesign["schema_version"] as? String, version == "2.0",
               let activeId = redesign["active_revision_id"] as? String,
               var revisions = redesign["revisions"] as? [[String: Any]] {
                if let revIdx = revisions.firstIndex(where: { ($0["id"] as? String) == activeId }) {
                    var rev = revisions[revIdx]
                    rev["overlays"] = overlays
                    revisions[revIdx] = rev
                    redesign["revisions"] = revisions
                    print("[RoomAR] Nudge: Updated overlay in active revision \(activeId) (v2.0)")
                }
            } else {
                redesign["overlays"] = overlays
                print("[RoomAR] Nudge: Updated overlay in root (v1.0)")
            }
            
            hudLabel?.text = " Nudge HUD [Selected Wall: \(selectedId.suffix(8))]\n x_min: \(String(format: "%.2f", xMin)) | x_max: \(String(format: "%.2f", xMax))\n y_min: \(String(format: "%.2f", yMin)) | y_max: \(String(format: "%.2f", yMax))"

            syncWallEntities()
        }
    }

    private func performCenterRaycast() {
        guard let arView = arView, selectedSurfaceId == nil else { return }
        
        let center = CGPoint(x: arView.bounds.midX, y: arView.bounds.midY)
        if let hitEntity = arView.entity(at: center) {
            var current: Entity? = hitEntity
            while let node = current {
                if !node.name.isEmpty && surfaces.contains(where: { ($0["id"] as? String) == node.name }) {
                    if pointedSurfaceId != node.name {
                        pointedSurfaceId = node.name
                        DispatchQueue.main.async { [weak self] in
                            self?.updateWallMaterials()
                            self?.updateDictateButtonTitle()
                        }
                    }
                    return
                }
                current = node.parent
            }
        }
        
        if pointedSurfaceId != nil {
            pointedSurfaceId = nil
            DispatchQueue.main.async { [weak self] in
                self?.updateWallMaterials()
                self?.updateDictateButtonTitle()
            }
        }
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

    /// Listens until the speaker pauses (~2s of silence) or a 60s safety cap
    /// is hit, instead of a fixed short duration. The prior fixed 4s cutoff
    /// truncated any dictation longer than one short phrase — endAudio() mid
    /// -sentence made the recognizer finalize on whatever partial buffer it
    /// had, dropping everything said before the cutoff. Partial results reset
    /// the silence timer, so a normal breath between sentences doesn't end
    /// the session early.
    static func recognize(from presenter: UIViewController, completion: @escaping (Result<String, Error>) -> Void) {
        guard let recognizer = SFSpeechRecognizer(), recognizer.isAvailable else {
            completion(.failure(NSError(domain: "Speech", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "Speech recognition unavailable.",
            ])))
            return
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
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

        var finished = false
        var silenceTimer: Timer?
        var safetyTimer: Timer?

        let stopListening = {
            silenceTimer?.invalidate()
            safetyTimer?.invalidate()
            audioEngine.stop()
            input.removeTap(onBus: 0)
            request.endAudio()
        }

        let resetSilenceTimer = {
            silenceTimer?.invalidate()
            silenceTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: false) { _ in
                stopListening()
            }
        }

        resetSilenceTimer()
        safetyTimer = Timer.scheduledTimer(withTimeInterval: 60.0, repeats: false) { _ in
            stopListening()
        }

        recognizer.recognitionTask(with: request) { result, error in
            guard !finished else { return }
            if let error {
                finished = true
                silenceTimer?.invalidate()
                safetyTimer?.invalidate()
                audioEngine.stop()
                input.removeTap(onBus: 0)
                completion(.failure(error))
                return
            }
            guard let result else { return }
            guard result.isFinal else {
                // Still talking — push the silence deadline back out.
                resetSilenceTimer()
                return
            }
            finished = true
            silenceTimer?.invalidate()
            safetyTimer?.invalidate()
            completion(.success(result.bestTranscription.formattedString))
        }
    }
}
#endif

import AVFoundation
