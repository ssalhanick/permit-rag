import Foundation

/// Resolves Capacitor Filesystem Directory.Data paths on iOS.
enum RoomScanPaths {
    static func dataDirectory() -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    static func fileURL(relativePath: String) -> URL {
        dataDirectory().appendingPathComponent(relativePath)
    }

    static func roomCapturePath(projectId: String, structureId: String, roomId: String) -> String {
        "room_scans/\(projectId)/\(structureId)/rooms/\(roomId)/capture.json"
    }

    static func redesignPath(projectId: String, structureId: String, roomId: String) -> String {
        "room_scans/\(projectId)/\(structureId)/rooms/\(roomId)/redesign.json"
    }

    /// Cache dir for on-device 3D model previews, keyed only by roomId — native
    /// capture doesn't know projectId/structureId yet (JS resolves those later),
    /// and a preview file doesn't need to be durable the way capture.json is.
    static func roomModelCacheURL(roomId: String) -> URL {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("room_models/\(roomId).usdz")
    }
}

enum RoomScanJSON {
    static func read(path: String) -> [String: Any]? {
        let url = RoomScanPaths.fileURL(relativePath: path)
        guard let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return json
    }

    static func write(path: String, object: [String: Any]) throws {
        let url = RoomScanPaths.fileURL(relativePath: path)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted])
        try data.write(to: url, options: .atomic)
    }
}
