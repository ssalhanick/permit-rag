import Foundation

/// Resolves Capacitor Filesystem Directory.Data paths on iOS.
enum RoomScanPaths {
    static func dataDirectory() -> URL {
        let library = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0]
        return library.appendingPathComponent("NoCloud", isDirectory: true)
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
