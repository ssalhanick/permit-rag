import React from "react";
import { Link } from "react-router-dom";

/**
 * Display structure/room scan rows from library or project links.
 *
 * @param {{
 *   scans: object[],
 *   emptyMessage?: string,
 *   onSetActive?: (scanId: string) => void,
 *   onUnlink?: (scanId: string) => void,
 *   showActive?: boolean,
 *   designHref?: (scanId: string) => string,
 * }} props
 */
export default function ScanLibraryList({
  scans,
  emptyMessage = "No scans yet.",
  onSetActive,
  onUnlink,
  showActive = false,
  designHref,
}) {
  if (!scans?.length) {
    return <p className="muted">{emptyMessage}</p>;
  }

  const structures = scans.filter((s) => s.scan_type === "structure");
  const rooms = scans.filter((s) => s.scan_type === "room");

  return (
    <div className="scan-library-list">
      {structures.map((structure) => {
        const childRooms = rooms.filter((r) => r.parent_scan_id === structure.id);
        return (
          <article key={structure.id} className="scan-library-structure">
            <header>
              <h4>{structure.structure_label || structure.room_label || "Structure"}</h4>
              <span className="muted">
                {childRooms.length || structure.derived?.room_count || 0} room(s) ·{" "}
                {new Date(structure.captured_at).toLocaleDateString()}
              </span>
            </header>
            {childRooms.length > 0 && (
              <ul className="room-scan-room-list">
                {childRooms.map((room) => (
                  <li key={room.id} className={room.is_active ? "active-room" : ""}>
                    <span>
                      {room.room_label}
                      {showActive && room.is_active ? " (active)" : ""}
                    </span>
                    <div className="scan-library-actions">
                      {onSetActive && (
                        <button type="button" className="text-button" onClick={() => onSetActive(room.id)}>
                          Set active
                        </button>
                      )}
                      {onUnlink && (
                        <button type="button" className="text-button" onClick={() => onUnlink(room.id)}>
                          Remove
                        </button>
                      )}
                      {designHref && (
                        <Link to={designHref(room.id)} className="text-button">
                          Design
                        </Link>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </article>
        );
      })}

      {rooms
        .filter((r) => !r.parent_scan_id || !structures.some((s) => s.id === r.parent_scan_id))
        .map((room) => (
          <article key={room.id} className="scan-library-structure">
            <header>
              <h4>{room.room_label}</h4>
              <span className="muted">{room.scan_type} · {new Date(room.captured_at).toLocaleDateString()}</span>
            </header>
            <div className="scan-library-actions">
              {showActive && room.is_active && <span className="badge">Active</span>}
              {onSetActive && (
                <button type="button" className="text-button" onClick={() => onSetActive(room.id)}>
                  Set active
                </button>
              )}
              {onUnlink && (
                <button type="button" className="text-button" onClick={() => onUnlink(room.id)}>
                  Remove
                </button>
              )}
              {designHref && (
                <Link to={designHref(room.id)} className="text-button">
                  Design
                </Link>
              )}
            </div>
            {room.derived && (
              <p className="muted">
                {room.derived.wall_count} walls · {room.derived.max_ceiling_height_m}m ceiling
              </p>
            )}
          </article>
        ))}
    </div>
  );
}
