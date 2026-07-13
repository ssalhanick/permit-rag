import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { fetchUserRoomScans } from "../api.js";
import { loadUserLibrary } from "../services/roomScanStorage.js";
import { isNativePlatform } from "../platform.js";

/**
 * Home page promo for room scan library.
 */
export default function RoomScansHomePromo() {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!user) {
      return;
    }
    (async () => {
      try {
        const res = await fetchUserRoomScans();
        setCount((res.data || []).length);
      } catch {
        const local = await Promise.resolve(loadUserLibrary());
        setCount(local?.length || 0);
      }
    })();
  }, [user]);

  if (!user) {
    return null;
  }

  return (
    <section className="panel room-scans-home-promo" aria-label="Room scans">
      <div className="room-scans-home-promo-inner">
        <div>
          <h2>Room Scans</h2>
          <p className="muted">
            Scan houses and rooms on {isNativePlatform() ? "your phone" : "mobile"}, keep them in your library,
            then link scans to any project for permit queries and AR design.
          </p>
          {count > 0 && (
            <p>
              <strong>{count}</strong> scan{count === 1 ? "" : "s"} in your library
            </p>
          )}
        </div>
        <div className="room-scans-home-actions">
          <Link to="/profile/room-scans" className="primary-button">
            Open scan library
          </Link>
          <Link to="/projects" className="secondary-button">
            Link to a project
          </Link>
        </div>
      </div>
    </section>
  );
}
