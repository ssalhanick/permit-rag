/**
 * pushNotifications.js — register for FCM/APNs on native.
 */

import { PushNotifications } from "@capacitor/push-notifications";
import { isNativePlatform } from "../platform.js";

/** True when FCM/APNs is wired (google-services.json + Firebase project). */
export function isPushNotificationsEnabled() {
  return import.meta.env?.VITE_PUSH_NOTIFICATIONS_ENABLED === "true";
}

/**
 * Initialize push notification listeners and request permission.
 *
 * Skipped by default until Firebase is configured — register() crashes
 * on Android without google-services.json (Phase 0 device gates).
 *
 * @returns {Promise<void>}
 */
export async function initPushNotifications() {
  if (!isNativePlatform() || !isPushNotificationsEnabled()) {
    return;
  }
  const perm = await PushNotifications.requestPermissions();
  if (perm.receive !== "granted") {
    return;
  }
  await PushNotifications.register();
  PushNotifications.addListener("registration", (token) => {
    console.info("[push] device token:", token.value);
  });
  PushNotifications.addListener("registrationError", (err) => {
    console.warn("[push] registration error:", err);
  });
  PushNotifications.addListener("pushNotificationReceived", (notification) => {
    console.info("[push] received:", notification);
  });
}
