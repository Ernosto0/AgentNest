/* Pivoris service worker: Web Push only.
 *
 * It exists so the browser can wake the app to show a notification and open it on click. It has
 * NO fetch handler and NO cache: every request goes straight to the network, so it can never
 * serve a stale page, a stale API answer, or anything from one user to another. Do not add
 * caching here without a design review (offline behaviour is out of scope).
 *
 * The push payload is JSON: { title, body, url, tag }. It is untrusted data: the title and body
 * are shown as plain text, and `url` is only ever opened if it resolves to this app's own origin.
 */

const FALLBACK_TITLE = "Pivoris";
const FALLBACK_URL = "/";
const ICON = "/icon-192.png";

/** A same-origin URL (as a string), or "/" for anything else, including other origins. */
function safeUrl(value) {
  try {
    if (typeof value !== "string" || value === "") return FALLBACK_URL;
    const resolved = new URL(value, self.location.origin);
    if (resolved.origin !== self.location.origin) return FALLBACK_URL;
    return resolved.pathname + resolved.search + resolved.hash;
  } catch (_error) {
    return FALLBACK_URL;
  }
}

function text(value, max) {
  return typeof value === "string" ? value.slice(0, max) : "";
}

function readPayload(event) {
  if (!event.data) return {};
  try {
    const data = event.data.json();
    return data && typeof data === "object" ? data : {};
  } catch (_error) {
    return {};
  }
}

// A new version of this file takes over at once; there is no cache to migrate.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  const data = readPayload(event);
  const tag = text(data.tag, 100);
  event.waitUntil(
    self.registration.showNotification(text(data.title, 120) || FALLBACK_TITLE, {
      body: text(data.body, 300),
      icon: ICON,
      badge: ICON,
      // A tag replaces an earlier notification for the same thing instead of stacking.
      ...(tag ? { tag } : {}),
      data: { url: safeUrl(data.url) },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(safeUrl(event.notification.data && event.notification.data.url), self.location.origin);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (new URL(client.url).origin === self.location.origin && "navigate" in client) {
          return client
            .focus()
            .then(() => client.navigate(target.href))
            .catch(() => self.clients.openWindow(target.href));
        }
      }
      return self.clients.openWindow(target.href);
    }),
  );
});
