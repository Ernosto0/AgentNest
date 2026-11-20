import { api, unwrap } from "@/api/client";

/** Where the push-only service worker lives. It has no fetch handler and no cache. */
export const SERVICE_WORKER_URL = "/sw.js";

/**
 * The worker is registered in production builds only, or when `VITE_ENABLE_SW=true` is set for
 * local testing. A plain dev server never registers one, so it cannot serve stale files.
 */
export function serviceWorkerEnabled(): boolean {
  return import.meta.env.PROD || import.meta.env.VITE_ENABLE_SW === "true";
}

export function registerServiceWorker(): void {
  if (!serviceWorkerEnabled() || !("serviceWorker" in navigator)) return;
  const register = () => {
    navigator.serviceWorker.register(SERVICE_WORKER_URL, { scope: "/" }).catch(() => {
      // A failed registration only means no push; the app works without it.
    });
  };
  if (document.readyState === "complete") register();
  else window.addEventListener("load", register, { once: true });
}

export function pushSupported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** `applicationServerKey` wants bytes; the server sends the VAPID public key as base64url. */
export function urlBase64ToBytes(value: string): Uint8Array<ArrayBuffer> {
  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export type PushOutcome =
  | { status: "subscribed"; id: string; label: string }
  | { status: "unsupported" | "disabled" | "denied" };

// --- device ownership and the opt-in prompt (F-01 part 2) --------------------------------------
//
// The browser has ONE push subscription per origin, shared by every workspace and every account
// that signs in on it. The server keeps one row per (workspace, user, endpoint). To keep a phone
// from buzzing for someone who is no longer using it, this browser remembers which user the
// subscription was made for and which server row it registered in each workspace:
//   - signing out revokes this device's rows for that user and drops the browser subscription;
//   - a different user subscribing on this browser first drops the previous user's subscription;
//   - turning it off in the last workspace that uses it drops the browser subscription too.
// Switching workspace needs nothing: the subscription belongs to the user and the device, and a
// workspace only pushes to a device registered there by a user who opted in.

const PREFIX = "pivoris.push.";
const deviceKey = (userId: string, workspaceId: string) => `${PREFIX}device.${userId}.${workspaceId}`;
const ownerKey = `${PREFIX}owner`;
const opportunityKey = (userId: string, workspaceId: string) =>
  `${PREFIX}opportunity.${userId}.${workspaceId}`;
const dismissedKey = (userId: string, workspaceId: string) =>
  `${PREFIX}dismissed.${userId}.${workspaceId}`;

/** Fired when the owner approves something, so an open prompt can appear without a reload. */
export const PUSH_OPPORTUNITY_EVENT = "pivoris:push-opportunity";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // private mode or blocked storage: the prompt simply does not remember
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

export function storedDeviceId(userId: string, workspaceId: string): string | null {
  return read(deviceKey(userId, workspaceId));
}

/** The first approval is the moment to offer notifications; later ones do not ask again. */
export function notePushOpportunity(userId: string, workspaceId: string): void {
  if (read(opportunityKey(userId, workspaceId)) === null) {
    write(opportunityKey(userId, workspaceId), "1");
  }
  window.dispatchEvent(new Event(PUSH_OPPORTUNITY_EVENT));
}

export function hasPushOpportunity(userId: string, workspaceId: string): boolean {
  return read(opportunityKey(userId, workspaceId)) !== null;
}

export function dismissPushPrompt(userId: string, workspaceId: string): void {
  write(dismissedKey(userId, workspaceId), "1");
}

export function pushPromptDismissed(userId: string, workspaceId: string): boolean {
  return read(dismissedKey(userId, workspaceId)) !== null;
}

/** iPhone, iPad or iPod (iPadOS 13+ reports itself as a Mac with a touch screen). */
export function isIosDevice(): boolean {
  const ua = navigator.userAgent ?? "";
  if (/iPhone|iPad|iPod/.test(ua)) return true;
  return navigator.platform === "MacIntel" && (navigator.maxTouchPoints ?? 0) > 1;
}

/** True when launched from the home screen (installed), where iOS allows Web Push. */
export function isStandalone(): boolean {
  const standalone = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return (
    standalone ||
    (typeof window.matchMedia === "function" && window.matchMedia("(display-mode: standalone)").matches)
  );
}

/** iOS delivers pushes only to an installed web app (iOS 16.4+): in Safari we guide, not ask. */
export function needsHomeScreenInstall(): boolean {
  return isIosDevice() && !isStandalone();
}

export type PushPermission = NotificationPermission | "unsupported";

export function pushPermission(): PushPermission {
  return "Notification" in window ? Notification.permission : "unsupported";
}

async function browserSubscription(): Promise<PushSubscription | null> {
  if (!("serviceWorker" in navigator)) return null;
  const registration = await navigator.serviceWorker.getRegistration(SERVICE_WORKER_URL);
  return (await registration?.pushManager.getSubscription()) ?? null;
}

/** Another user's subscription must not follow a new sign-in: drop it so a fresh endpoint is made. */
async function releaseForeignSubscription(userId: string): Promise<void> {
  const owner = read(ownerKey);
  if (owner && owner !== userId) {
    await (await browserSubscription())?.unsubscribe();
    write(ownerKey, null);
  }
}

/**
 * Ask for permission, subscribe this browser and register it with the server. With `userId` the
 * device is remembered for that user (see the notes above); without it (developer test) it is not.
 */
export async function subscribeThisDevice(
  workspaceId: string,
  userId?: string,
): Promise<PushOutcome> {
  if (!pushSupported()) return { status: "unsupported" };
  const path = { workspace_id: workspaceId };
  const config = await unwrap(
    api.GET("/api/v1/workspaces/{workspace_id}/push-subscriptions/config", { params: { path } }),
  );
  if (!config.enabled || !config.public_key) return { status: "disabled" };
  if ((await Notification.requestPermission()) !== "granted") return { status: "denied" };
  if (userId) await releaseForeignSubscription(userId);

  const registration =
    (await navigator.serviceWorker.getRegistration(SERVICE_WORKER_URL)) ??
    (await navigator.serviceWorker.register(SERVICE_WORKER_URL, { scope: "/" }));
  await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToBytes(config.public_key),
    }));
  const json = subscription.toJSON();
  const device = await unwrap(
    api.POST("/api/v1/workspaces/{workspace_id}/push-subscriptions", {
      params: { path },
      body: {
        endpoint: subscription.endpoint,
        expirationTime: json.expirationTime ?? null,
        keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
      },
    }),
  );
  if (userId) {
    write(deviceKey(userId, workspaceId), device.id);
    write(ownerKey, userId);
  }
  return { status: "subscribed", id: device.id, label: device.label };
}

function otherDevicesRemain(userId: string, exceptWorkspaceId: string): boolean {
  const prefix = `${PREFIX}device.${userId}.`;
  try {
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (key?.startsWith(prefix) && key !== deviceKey(userId, exceptWorkspaceId)) return true;
    }
  } catch {
    // ignore
  }
  return false;
}

/**
 * Remove one registered device on the server. The browser's own subscription is dropped too,
 * unless (with `userId`) this browser is still registered for the same user in another workspace.
 */
export async function unsubscribeThisDevice(
  workspaceId: string,
  deviceId: string,
  userId?: string,
): Promise<void> {
  await unwrap(
    api.DELETE("/api/v1/workspaces/{workspace_id}/push-subscriptions/{subscription_id}", {
      params: { path: { workspace_id: workspaceId, subscription_id: deviceId } },
    }),
  );
  if (userId) {
    if (storedDeviceId(userId, workspaceId) === deviceId) write(deviceKey(userId, workspaceId), null);
    if (otherDevicesRemain(userId, workspaceId)) return;
    write(ownerKey, null);
  }
  await (await browserSubscription())?.unsubscribe();
}

/**
 * Sign-out hygiene: revoke this browser's registrations for the user in each workspace (best
 * effort, while the session still works) and drop the browser subscription. Never throws.
 */
export async function forgetThisDevice(userId: string, workspaceIds: string[]): Promise<void> {
  try {
    await Promise.all(
      workspaceIds.map(async (workspaceId) => {
        const deviceId = storedDeviceId(userId, workspaceId);
        if (!deviceId) return;
        write(deviceKey(userId, workspaceId), null);
        try {
          await unwrap(
            api.DELETE("/api/v1/workspaces/{workspace_id}/push-subscriptions/{subscription_id}", {
              params: { path: { workspace_id: workspaceId, subscription_id: deviceId } },
            }),
          );
        } catch {
          // already gone or offline: the server drops a dead device on its next push
        }
      }),
    );
    if (read(ownerKey) === userId) {
      write(ownerKey, null);
      await (await browserSubscription())?.unsubscribe();
    }
  } catch {
    // signing out must work even when push cleanup does not
  }
}
