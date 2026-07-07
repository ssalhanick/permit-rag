import React, { useEffect, useState } from "react";
import { Network } from "@capacitor/network";
import { isNativePlatform } from "../platform.js";

/**
 * OfflineBanner — shows connection status on native; no-op on web.
 */
export default function OfflineBanner() {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    if (!isNativePlatform()) {
      const onStatus = () => setOnline(navigator.onLine);
      window.addEventListener("online", onStatus);
      window.addEventListener("offline", onStatus);
      setOnline(navigator.onLine);
      return () => {
        window.removeEventListener("online", onStatus);
        window.removeEventListener("offline", onStatus);
      };
    }
    let handle = null;
    Network.getStatus().then((s) => setOnline(s.connected));
    Network.addListener("networkStatusChange", (s) => setOnline(s.connected)).then((h) => {
      handle = h;
    });
    return () => {
      handle?.remove();
    };
  }, []);

  if (online) {
    return null;
  }

  return (
    <div className="offline-banner" role="status">
      No connection — some features need network. Cached views still work.
    </div>
  );
}
