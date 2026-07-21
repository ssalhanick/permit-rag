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
        ]
    }

    static func encodeStructure(
        rooms: [CapturedRoom],
        labels: [String],
        sections: [String?],
        structureLabel: String,
        structureId: String
    ) -> [String: Any] {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        let capturedAt = formatter.string(from: Date())

        var roomPayloads: [[String: Any]] = []
        for (index, room) in rooms.enumerated() {
            let roomId = UUID().uuidString.lowercased()
            let label = index < labels.count ? labels[index] : "Room \(index + 1)"
            let section = index < sections.count ? sections[index] : nil
            let encoded = encode(capturedRoom: room, roomLabel: label, roomId: String(roomId))
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

    private static func encodeSurface(
        _ surface: CapturedRoom.Surface,
        category: String,
        prefix: String,
        index: Int
    ) -> [String: Any] {
        let transform = surface.transform
        let position = transform.columns.3
        let dims = surface.dimensions

        return [
            "id": "\(prefix)-\(index)",
            "category": category,
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
