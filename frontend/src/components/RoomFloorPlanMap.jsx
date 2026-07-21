import React, { useMemo } from "react";
import { buildFloorPlanLayout } from "../services/roomFloorPlan.js";

const CATEGORY_LABEL = {
  wall: "Wall",
  door: "Door",
  window: "Window",
  opening: "Opening",
  floor: "Floor",
};

/**
 * Top-down 2D clickable floor plan, projected from the same capture.json
 * surfaces (transform_matrix + dimensions) the native AR view renders.
 * Lets you pick a surface without being in the live AR session, then
 * optionally jump into AR with it pre-selected.
 *
 * @param {{
 *   surfaces: object[],
 *   selectedSurfaceId: string | null,
 *   onSelectSurface: (surfaceId: string | null) => void,
 * }} props
 */
export default function RoomFloorPlanMap({ surfaces, selectedSurfaceId, onSelectSurface }) {
  const layout = useMemo(() => buildFloorPlanLayout(surfaces || []), [surfaces]);

  const hasGeometry = layout.walls.length > 0 || layout.floors.length > 0;
  if (!hasGeometry) {
    return null;
  }

  const padding = 0.4;
  const { minX, maxX, minY, maxY } = layout.bounds;
  const viewBox = [
    minX - padding,
    minY - padding,
    maxX - minX + padding * 2,
    maxY - minY + padding * 2,
  ].join(" ");

  const handleClick = (surfaceId) => {
    onSelectSurface?.(surfaceId === selectedSurfaceId ? null : surfaceId);
  };

  const strokeFor = (id) => (id === selectedSurfaceId ? "var(--accent, #14b8a6)" : "var(--foreground, #1f2933)");
  const widthFor = (id) => (id === selectedSurfaceId ? 0.12 : 0.06);

  const selectedShape = [...layout.walls, ...layout.doors, ...layout.windows, ...layout.openings, ...layout.floors]
    .find((s) => s.id === selectedSurfaceId);

  return (
    <figure className="room-floor-plan-map" aria-label="Room floor plan">
      <svg viewBox={viewBox} role="img" aria-label="Top-down room floor plan">
        {layout.floors.map((floor) => (
          <polygon
            key={floor.id}
            points={floor.points.map((p) => p.join(",")).join(" ")}
            className="room-floor-plan-floor"
            fill="var(--surface-muted, #f1f5f4)"
            stroke="none"
            onClick={floor.id === "__fallback_floor" ? undefined : () => handleClick(floor.id)}
            style={{ cursor: floor.id === "__fallback_floor" ? "default" : "pointer" }}
          />
        ))}
        {layout.walls.map((wall) => (
          <line
            key={wall.id}
            x1={wall.x1}
            y1={wall.y1}
            x2={wall.x2}
            y2={wall.y2}
            stroke={strokeFor(wall.id)}
            strokeWidth={widthFor(wall.id)}
            strokeLinecap="round"
            onClick={() => handleClick(wall.id)}
            className="room-floor-plan-wall"
          />
        ))}
        {[...layout.doors, ...layout.windows, ...layout.openings].map((surface) => (
          <line
            key={surface.id}
            x1={surface.x1}
            y1={surface.y1}
            x2={surface.x2}
            y2={surface.y2}
            stroke={strokeFor(surface.id)}
            strokeWidth={surface.id === selectedSurfaceId ? 0.14 : 0.1}
            strokeLinecap="butt"
            strokeDasharray={surface.category === "window" ? "0.1 0.06" : undefined}
            onClick={() => handleClick(surface.id)}
            className={`room-floor-plan-${surface.category}`}
          />
        ))}
      </svg>
      <figcaption className="muted room-floor-plan-caption">
        {selectedShape
          ? `Selected: ${CATEGORY_LABEL[selectedShape.category] || "Surface"} (${selectedShape.id})`
          : "Tap a wall, door, window, or floor to select it."}
      </figcaption>
    </figure>
  );
}
