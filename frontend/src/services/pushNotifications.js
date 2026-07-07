/**
 * pushNotifications.js — register for FCM/APNs on native.
 */

import { PushNotifications } from "@capacitor/push-notifications";
import { isNativePlatform } from "../platform.js";

/**
 * Initialize push notification listeners and request permission.
 *
 * @returns {Promise<void>}
 */
export async function initPushNotifications() {
  if (!isNativePlatform()) {
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
