import Foundation

#if canImport(RoomPlan)
import RoomPlan
import simd

/// Converts RoomPlan captures into interchange JSON schema v1.0 / v2.0.
enum RoomCaptureEncoder {

    static func encode(capturedRoom: CapturedRoom, roomLabel: String, roomId: String? = nil) -> [String: Any] {
        let rid = (roomId ?? UUID().uuidString).lowercased()
        var surfaces: [[String: Any]] = []
        surfaces.append(contentsOf: capturedRoom.walls.enumerated().map {
            encodeSurface($0.element, category: "wall", prefix: "\(rid)-wall", index: $0.offset)
        })
        surfaces.append(contentsOf: capturedRoom.doors.enumerated().map {
            encodeSurface($0.element, category: "door", prefix: "\(rid)-door", index: $0.offset)
        })
        surfaces.append(contentsOf: capturedRoom.windows.enumerated().map {
            encodeSurface($0.element, category: "window", prefix: "\(rid)-window", index: $0.offset)
        })
        surfaces.append(contentsOf: capturedRoom.openings.enumerated().map {
            encodeSurface($0.element, category: "opening", prefix: "\(rid)-opening", index: $0.offset)
        })
        if #available(iOS 17.0, *) {
            surfaces.append(contentsOf: capturedRoom.floors.enumerated().map {
                encodeSurface($0.element, category: "floor", prefix: "\(rid)-floor", index: $0.offset)
            })
        }

        // Fixtures/appliances RoomPlan detects (sinks, refrigerators, etc.) — kept
        // separate from "surfaces" since they aren't planar/paintable and the AR
        // viewer's tap-to-apply-material flow shouldn't pick them up.
        let objects = capturedRoom.objects.enumerated().map {
            encodeObject($0.element, prefix: "\(rid)-object", index: $0.offset)
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]

        return [
            "schema_version": "1.0",
            "scan_type": "room",
            "room_id": rid,
            "room_label": roomLabel,
            "captured_at": formatter.string(from: Date()),
            "units": "meters",
            "surfaces": surfaces,
            "objects": objects,
        ]
    }

    static func encodeStructure(
        rooms: [CapturedRoom],
        labels: [String],
        sections: [String?],
        roomIds: [String],
        structureLabel: String,
        structureId: String
    ) -> [String: Any] {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        let capturedAt = formatter.string(from: Date())

        var roomPayloads: [[String: Any]] = []
        for (index, room) in rooms.enumerated() {
            let roomId = index < roomIds.count ? roomIds[index] : UUID().uuidString.lowercased()
            let label = index < labels.count ? labels[index] : "Room \(index + 1)"
            let section = index < sections.count ? sections[index] : nil
            let encoded = encode(capturedRoom: room, roomLabel: label, roomId: roomId)
            var payload = encoded
            payload["label"] = label
            payload["section"] = section as Any
            roomPayloads.append(payload)
        }

        return [
            "schema_version": "2.0",
            "scan_type": "structure",
            "structure_id": structureId,
            "structure_label": structureLabel,
            "captured_at": capturedAt,
            "units": "meters",
            "rooms": roomPayloads,
        ]
    }

    /// Best-effort on-device 3D preview export — not fatal on failure (e.g.
    /// CapturedRoom.Error.deviceNotSupported), and not on the critical path
    /// for resolving the capture call, so this runs fire-and-forget.
    static func exportModelPreview(_ capturedRoom: CapturedRoom, roomId: String) {
        let url = RoomScanPaths.roomModelCacheURL(roomId: roomId)
        DispatchQueue.global(qos: .utility).async {
            do {
                try FileManager.default.createDirectory(
                    at: url.deletingLastPathComponent(),
                    withIntermediateDirectories: true
                )
                try capturedRoom.export(to: url)
                print("[RoomCaptureEncoder] USDZ preview exported for \(roomId) -> \(url.path)")
            } catch {
                print("[RoomCaptureEncoder] USDZ preview export failed for \(roomId): \(error.localizedDescription)")
            }
        }
    }

    private static func encodeSurface(
        _ surface: CapturedRoom.Surface,
        category: String,
        prefix: String,
        index: Int
    ) -> [String: Any] {
        let transform = surface.transform
        let position = transform.columns.3
        let dims = surface.dimensions

        var payload: [String: Any] = [
            "id": "\(prefix)-\(index)",
            "native_id": surface.identifier.uuidString,
            "category": category,
            "confidence": confidenceString(surface.confidence),
            "position": [
                "x": Double(position.x),
                "y": Double(position.y),
                "z": Double(position.z),
            ],
            "dimensions": [
                "width": Double(dims.x),
                "height": Double(dims.y),
                "depth": Double(dims.z),
            ],
            "transform_matrix": matrixArray(transform),
        ]

        // Real polygon outline (vs. just a bounding box) — local to this
        // surface, same space `dimensions` is in; the AR viewer applies
        // transform_matrix on the parent entity to place it in the room.
        if #available(iOS 17.0, *) {
            payload["polygon_corners"] = surface.polygonCorners.map { corner in
                ["x": Double(corner.x), "y": Double(corner.y), "z": Double(corner.z)]
            }
        }

        return payload
    }

    private static func encodeObject(
        _ object: CapturedRoom.Object,
        prefix: String,
        index: Int
    ) -> [String: Any] {
        let transform = object.transform
        let position = transform.columns.3
        let dims = object.dimensions

        return [
            "id": "\(prefix)-\(index)",
            "native_id": object.identifier.uuidString,
            "category": categoryString(object.category),
            "confidence": confidenceString(object.confidence),
            "position": [
                "x": Double(position.x),
                "y": Double(position.y),
                "z": Double(position.z),
            ],
            "dimensions": [
                "width": Double(dims.x),
                "height": Double(dims.y),
                "depth": Double(dims.z),
            ],
            "transform_matrix": matrixArray(transform),
        ]
    }

    private static func confidenceString(_ confidence: CapturedRoom.Confidence) -> String {
        switch confidence {
        case .high: return "high"
        case .medium: return "medium"
        case .low: return "low"
        @unknown default: return "unknown"
        }
    }

    private static func categoryString(_ category: CapturedRoom.Object.Category) -> String {
        switch category {
        case .storage: return "storage"
        case .refrigerator: return "refrigerator"
        case .stove: return "stove"
        case .bed: return "bed"
        case .sink: return "sink"
        case .washerDryer: return "washer_dryer"
        case .toilet: return "toilet"
        case .bathtub: return "bathtub"
        case .oven: return "oven"
        case .dishwasher: return "dishwasher"
        case .table: return "table"
        case .sofa: return "sofa"
        case .chair: return "chair"
        case .fireplace: return "fireplace"
        case .television: return "television"
        case .stairs: return "stairs"
        @unknown default: return "other"
        }
    }

    private static func matrixArray(_ matrix: simd_float4x4) -> [Double] {
        [
            Double(matrix.columns.0.x), Double(matrix.columns.0.y), Double(matrix.columns.0.z), Double(matrix.columns.0.w),
            Double(matrix.columns.1.x), Double(matrix.columns.1.y), Double(matrix.columns.1.z), Double(matrix.columns.1.w),
            Double(matrix.columns.2.x), Double(matrix.columns.2.y), Double(matrix.columns.2.z), Double(matrix.columns.2.w),
            Double(matrix.columns.3.x), Double(matrix.columns.3.y), Double(matrix.columns.3.z), Double(matrix.columns.3.w),
        ]
    }
}
#endif
