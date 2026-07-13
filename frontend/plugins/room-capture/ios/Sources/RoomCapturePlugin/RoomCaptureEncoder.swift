import Foundation

#if canImport(RoomPlan)
import RoomPlan
import simd

/// Converts RoomPlan CapturedRoom into interchange JSON schema v1.0.
enum RoomCaptureEncoder {

    static func encode(capturedRoom: CapturedRoom, roomLabel: String) -> [String: Any] {
        var surfaces: [[String: Any]] = []
        surfaces.append(contentsOf: capturedRoom.walls.map { encodeSurface($0, category: "wall") })
        surfaces.append(contentsOf: capturedRoom.doors.map { encodeSurface($0, category: "door") })
        surfaces.append(contentsOf: capturedRoom.windows.map { encodeSurface($0, category: "window") })
        surfaces.append(contentsOf: capturedRoom.openings.map { encodeSurface($0, category: "opening") })

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]

        return [
            "schema_version": "1.0",
            "room_label": roomLabel,
            "captured_at": formatter.string(from: Date()),
            "units": "meters",
            "surfaces": surfaces,
        ]
    }

    private static func encodeSurface(_ surface: CapturedRoom.Surface, category: String) -> [String: Any] {
        let transform = surface.transform
        let position = transform.columns.3
        let dims = surface.dimensions

        return [
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
