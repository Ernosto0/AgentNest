import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { approval, BASE } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, WS_HARBOR, workspace } from "@/test/fixtures";
import { json, mockApi, noContent } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { forgetThisDevice, notePushOpportunity, storedDeviceId } from "@/pwa/push";

const USER = ME.user.id;
const DEVICE_ID = "d1000000-0000-4000-8000-000000000001";
const PUSH = `${BASE}/push-subscriptions`;
const PUBLIC_KEY = "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U";
const SETTINGS = `/w/${WS_GOLKENT}/more/settings/connections`;
const OFF = { approvals: false, questions: false, failures: false };

afterEach(() => {
  vi.unstubAllGlobals();
  for (const name of ["serviceWorker", "userAgent", "maxTouchPoints", "platform", "standalone"]) {
    try {
      delete (navigator as unknown as Record<string, unknown>)[name];
    } catch {
      // not an own property
    }
  }
  delete (window as unknown as Record<string, unknown>).PushManager;
});

interface BrowserOptions {
  permission?: NotificationPermission;
  subscribed?: boolean;
}

/** A browser that can receive pushes: Notification, PushManager and a service worker registration. */
function stubBrowser({ permission = "default", subscribed = false }: BrowserOptions = {}) {
  const state = { permission, unsubscribed: 0, requested: 0 };
  const subscription = {
    endpoint: "https://fcm.googleapis.com/fcm/send/test-device",
    toJSON: () => ({ endpoint: "https://fcm.googleapis.com/fcm/send/test-device", expirationTime: null, keys: { p256dh: "p", auth: "a" } }),
    unsubscribe: vi.fn(async () => {
      state.unsubscribed += 1;
      return true;
    }),
  };
  let current: typeof subscription | null = subscribed ? subscription : null;
  const registration = {
    pushManager: {
      getSubscription: vi.fn(async () => current),
      subscribe: vi.fn(async () => {
        current = subscription;
        return subscription;
      }),
    },
  };
  vi.stubGlobal(
    "Notification",
    Object.assign(function Notification() {}, {
      get permission() {
        return state.permission;
      },
      requestPermission: vi.fn(async () => {
        state.requested += 1;
        state.permission = "granted";
        return "granted" as NotificationPermission;
      }),
    }),
  );
  window.PushManager = class {} as unknown as typeof PushManager;
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      getRegistration: vi.fn(async () => registration),
      register: vi.fn(async () => registration),
      ready: Promise.resolve(registration),
    },
  });
  return { state, subscription, registration };
}

function stubIosSafari() {
  Object.defineProperty(navigator, "userAgent", {
    configurable: true,
    value: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1",
  });
}

function routes(extra: Record<string, () => Response> = {}, enabled = true) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/channels/links`]: () => json([]),
    [`GET ${PUSH}/config`]: () => json(enabled ? { enabled: true, public_key: PUBLIC_KEY } : { enabled: false, public_key: null }),
    [`GET ${PUSH}/preferences`]: () => json(OFF),
    [`GET ${PUSH}`]: () => json({ items: [] }),
    [`GET ${BASE}/approvals`]: () => json({ items: [], next_cursor: null }),
    ...extra,
  };
}

describe("phone notification settings", () => {
  it("shows nothing at all when the server has no push keys", async () => {
    stubBrowser();
    mockApi(routes({}, false));
    renderApp(SETTINGS);
    expect(await screen.findByText("Telegram bağlantısı")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("push-settings")).not.toBeInTheDocument());
  });

  it("lists the three categories, all off until switched on, and saves each choice", async () => {
    stubBrowser();
    const requests = mockApi(
      routes({
        [`PUT ${PUSH}/preferences`]: () => json({ ...OFF, approvals: true }),
      }),
    );
    renderApp(SETTINGS);
    const panel = await screen.findByTestId("push-settings");
    const approvals = within(panel).getByRole("checkbox", { name: /Beni bekleyen onaylar/ });
    expect(approvals).not.toBeChecked();
    expect(within(panel).getByRole("checkbox", { name: /Asistanımın soruları/ })).not.toBeChecked();
    expect(within(panel).getByRole("checkbox", { name: /Sorunlar/ })).not.toBeChecked();
    expect(panel).toHaveTextContent("22:00 ile 08:00 arasında");

    await userEvent.setup().click(approvals);
    await waitFor(() => expect(requests.some((r) => r.method === "PUT")).toBe(true));
    expect(requests.find((r) => r.method === "PUT")!.body).toEqual({ approvals: true });
    await waitFor(() => expect(approvals).toBeChecked());
  });

  it("registers this device after asking permission and remembers it for the user", async () => {
    const browser = stubBrowser();
    let devices: unknown[] = [];
    const requests = mockApi(
      routes({
        [`GET ${PUSH}`]: () => json({ items: devices }),
        [`POST ${PUSH}`]: () => {
          devices = [{ id: DEVICE_ID, label: "Chrome on Android", created_at: "2026-11-16T09:00:00Z", last_success_at: null }];
          return json(devices[0], 201);
        },
      }),
    );
    renderApp(SETTINGS);
    const panel = await screen.findByTestId("push-settings");
    expect(within(panel).getByTestId("push-device-state")).toHaveTextContent("kapalı");

    await userEvent.setup().click(within(panel).getByRole("button", { name: "Bu cihazda aç" }));
    await waitFor(() => expect(within(panel).getByTestId("push-device-state")).toHaveTextContent("açık"));
    const post = requests.find((r) => r.method === "POST" && r.path.endsWith("/push-subscriptions"))!;
    expect(post.body).toMatchObject({ endpoint: "https://fcm.googleapis.com/fcm/send/test-device", keys: { p256dh: "p", auth: "a" } });
    expect(browser.state.requested).toBe(1);
    expect(storedDeviceId(USER, WS_GOLKENT)).toBe(DEVICE_ID);
    expect(within(panel).getByText("Chrome on Android")).toBeInTheDocument();
  });

  it("removes a device and drops the browser subscription when it was the last one", async () => {
    const browser = stubBrowser({ subscribed: true });
    window.localStorage.setItem(`agentnest.push.device.${USER}.${WS_GOLKENT}`, DEVICE_ID);
    window.localStorage.setItem("agentnest.push.owner", USER);
    let devices = [{ id: DEVICE_ID, label: "Chrome on Android", created_at: "2026-11-16T09:00:00Z", last_success_at: "2026-11-16T10:00:00Z" }];
    const requests = mockApi(
      routes({
        [`GET ${PUSH}`]: () => json({ items: devices }),
        [`DELETE ${PUSH}/${DEVICE_ID}`]: () => {
          devices = [];
          return noContent();
        },
      }),
    );
    renderApp(SETTINGS);
    const panel = await screen.findByTestId("push-settings");
    expect(await within(panel).findByTestId("push-device-state")).toHaveTextContent("açık");
    await userEvent.setup().click(within(panel).getByRole("button", { name: "Bu cihazda kapat" }));
    await waitFor(() => expect(requests.some((r) => r.method === "DELETE")).toBe(true));
    await waitFor(() => expect(browser.state.unsubscribed).toBe(1));
    expect(storedDeviceId(USER, WS_GOLKENT)).toBeNull();
    await waitFor(() => expect(within(panel).getByTestId("push-device-state")).toHaveTextContent("kapalı"));
  });

  it("explains a blocked permission instead of offering a button that cannot work", async () => {
    stubBrowser({ permission: "denied" });
    mockApi(routes());
    renderApp(SETTINGS);
    const panel = await screen.findByTestId("push-settings");
    expect(within(panel).getByRole("alert")).toHaveTextContent("engellenmiş");
    expect(within(panel).queryByRole("button", { name: "Bu cihazda aç" })).not.toBeInTheDocument();
  });

  it("says so when the browser cannot receive pushes", async () => {
    mockApi(routes()); // no service worker, no PushManager
    renderApp(SETTINGS);
    const panel = await screen.findByTestId("push-settings");
    expect(panel).toHaveTextContent("Bu tarayıcı bildirim alamıyor");
    expect(within(panel).queryByRole("button", { name: "Bu cihazda aç" })).not.toBeInTheDocument();
  });

  it("shows the Add to Home Screen guide instead of the button in iOS Safari", async () => {
    stubIosSafari();
    mockApi(routes());
    renderApp(SETTINGS);
    const panel = await screen.findByTestId("push-settings");
    const guide = within(panel).getByTestId("push-ios-guide");
    expect(guide).toHaveTextContent("Ana Ekrana Ekle");
    expect(within(panel).queryByRole("button", { name: "Bu cihazda aç" })).not.toBeInTheDocument();
  });

  it("is available in English", async () => {
    stubBrowser();
    mockApi(routes());
    renderApp(SETTINGS);
    await screen.findByTestId("push-settings");
    const { setLanguage } = await import("@/i18n");
    await act(async () => setLanguage("en"));
    const panel = screen.getByTestId("push-settings");
    expect(within(panel).getByRole("heading", { name: "Phone notifications" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Turn on for this device" })).toBeInTheDocument();
    expect(within(panel).getByRole("checkbox", { name: /Approvals waiting for me/ })).toBeInTheDocument();
  });
});

describe("the notification prompt", () => {
  const HOME = `/w/${WS_GOLKENT}/approvals`;

  it("does not appear on first load and does not even ask the server for the key", async () => {
    stubBrowser();
    const requests = mockApi(routes());
    renderApp(HOME);
    expect(await screen.findByText("Bekleyen onay yok")).toBeInTheDocument();
    expect(screen.queryByTestId("push-prompt")).not.toBeInTheDocument();
    expect(requests.some((r) => r.path.includes("push-subscriptions"))).toBe(false);
  });

  it("appears after the first approval, enables approvals on this device, then closes", async () => {
    stubBrowser();
    const pending = approval();
    let devices: unknown[] = [];
    const requests = mockApi(
      routes({
        [`GET ${BASE}/approvals`]: () => json({ items: [pending], next_cursor: null }),
        [`POST ${BASE}/approvals/${pending.id}/decision`]: () => json(approval({ status: "approved" })),
        [`GET ${PUSH}`]: () => json({ items: devices }),
        [`POST ${PUSH}`]: () => {
          devices = [{ id: DEVICE_ID, label: "Chrome on Android", created_at: "2026-11-16T09:00:00Z", last_success_at: null }];
          return json(devices[0], 201);
        },
        [`PUT ${PUSH}/preferences`]: () => json({ ...OFF, approvals: true }),
      }),
    );
    renderApp(HOME);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bilgi güncelleme/ }));
    expect(screen.queryByTestId("push-prompt")).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Onayla" }));

    const prompt = await screen.findByTestId("push-prompt");
    expect(prompt).toHaveTextContent("müşterilerinizin mesajları hiçbir zaman görünmez");
    // The decision sheet closes once the decision is saved; until then it holds the page.
    await waitFor(() => expect(screen.queryByTestId("approval-detail")).not.toBeInTheDocument());
    await user.click(within(prompt).getByRole("button", { name: "Bildirimleri aç" }));
    await waitFor(() => expect(screen.getByTestId("push-prompt")).toHaveTextContent("Bu cihaz için bildirimler açık"));
    expect(requests.find((r) => r.method === "PUT")!.body).toEqual({ approvals: true });
    expect(requests.some((r) => r.method === "POST" && r.path.endsWith("/push-subscriptions"))).toBe(true);
    await user.click(within(screen.getByTestId("push-prompt")).getByRole("button", { name: "Kapat" }));
    expect(screen.queryByTestId("push-prompt")).not.toBeInTheDocument();
  });

  it("is not shown again once dismissed, and a later approval does not bring it back", async () => {
    stubBrowser();
    mockApi(routes());
    renderApp(HOME);
    await screen.findByText("Bekleyen onay yok");
    act(() => notePushOpportunity(USER, WS_GOLKENT));
    const user = userEvent.setup();
    await user.click(await within(await screen.findByTestId("push-prompt")).findByRole("button", { name: "Şimdi değil" }));
    expect(screen.queryByTestId("push-prompt")).not.toBeInTheDocument();
    act(() => notePushOpportunity(USER, WS_GOLKENT));
    expect(screen.queryByTestId("push-prompt")).not.toBeInTheDocument();
  });

  it("is hidden when the server has no push keys", async () => {
    stubBrowser();
    mockApi(routes({}, false));
    renderApp(HOME);
    await screen.findByText("Bekleyen onay yok");
    act(() => notePushOpportunity(USER, WS_GOLKENT));
    await waitFor(() => expect(screen.queryByTestId("push-prompt")).not.toBeInTheDocument());
  });

  it("is not shown when the permission was already refused", async () => {
    stubBrowser({ permission: "denied" });
    mockApi(routes());
    renderApp(HOME);
    await screen.findByText("Bekleyen onay yok");
    act(() => notePushOpportunity(USER, WS_GOLKENT));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByTestId("push-prompt")).not.toBeInTheDocument();
  });

  it("shows the Add to Home Screen guide on iOS Safari instead of asking for permission", async () => {
    stubIosSafari();
    mockApi(routes());
    renderApp(HOME);
    await screen.findByText("Bekleyen onay yok");
    act(() => notePushOpportunity(USER, WS_GOLKENT));
    const prompt = await screen.findByTestId("push-prompt");
    expect(within(prompt).getByTestId("push-ios-guide")).toHaveTextContent("Ana Ekrana Ekle");
    expect(within(prompt).queryByRole("button", { name: "Bildirimleri aç" })).not.toBeInTheDocument();
    await userEvent.setup().click(within(prompt).getByRole("button", { name: "Anladım" }));
    expect(screen.queryByTestId("push-prompt")).not.toBeInTheDocument();
  });

  it("explains a refusal made in the permission dialog", async () => {
    const browser = stubBrowser();
    (Notification as unknown as { requestPermission: () => Promise<string> }).requestPermission = vi.fn(async () => {
      browser.state.permission = "denied";
      return "denied";
    });
    mockApi(routes());
    renderApp(HOME);
    await screen.findByText("Bekleyen onay yok");
    act(() => notePushOpportunity(USER, WS_GOLKENT));
    const prompt = await screen.findByTestId("push-prompt");
    await userEvent.setup().click(within(prompt).getByRole("button", { name: "Bildirimleri aç" }));
    expect(await within(prompt).findByRole("alert")).toHaveTextContent("engellenmiş");
  });
});

describe("signing out and switching", () => {
  it("revokes this browser's devices and drops its subscription on sign-out", async () => {
    const browser = stubBrowser({ subscribed: true });
    window.localStorage.setItem(`agentnest.push.device.${USER}.${WS_GOLKENT}`, DEVICE_ID);
    window.localStorage.setItem("agentnest.push.owner", USER);
    const requests = mockApi({
      [`DELETE ${PUSH}/${DEVICE_ID}`]: () => noContent(),
    });
    await forgetThisDevice(USER, [WS_GOLKENT, WS_HARBOR]);
    expect(requests.filter((r) => r.method === "DELETE").map((r) => r.path)).toEqual([`${PUSH}/${DEVICE_ID}`]);
    expect(browser.state.unsubscribed).toBe(1);
    expect(storedDeviceId(USER, WS_GOLKENT)).toBeNull();
    expect(window.localStorage.getItem("agentnest.push.owner")).toBeNull();
  });

  it("still signs out when the revoke fails", async () => {
    stubBrowser({ subscribed: true });
    window.localStorage.setItem(`agentnest.push.device.${USER}.${WS_GOLKENT}`, DEVICE_ID);
    window.localStorage.setItem("agentnest.push.owner", USER);
    mockApi({ [`DELETE ${PUSH}/${DEVICE_ID}`]: () => json({ code: "INTERNAL_ERROR", status: 500 }, 500) });
    await expect(forgetThisDevice(USER, [WS_GOLKENT])).resolves.toBeUndefined();
    expect(storedDeviceId(USER, WS_GOLKENT)).toBeNull();
  });

  it("drops another user's browser subscription before subscribing a new user", async () => {
    const browser = stubBrowser({ subscribed: true });
    window.localStorage.setItem("agentnest.push.owner", "11111111-1111-4111-8111-111111111111");
    mockApi(
      routes({
        [`POST ${PUSH}`]: () => json({ id: DEVICE_ID, label: "Chrome on Android", created_at: "2026-11-16T09:00:00Z", last_success_at: null }, 201),
      }),
    );
    renderApp(SETTINGS);
    const panel = await screen.findByTestId("push-settings");
    await userEvent.setup().click(within(panel).getByRole("button", { name: "Bu cihazda aç" }));
    await waitFor(() => expect(storedDeviceId(USER, WS_GOLKENT)).toBe(DEVICE_ID));
    expect(browser.state.unsubscribed).toBe(1); // the previous user's endpoint was dropped first
    expect(window.localStorage.getItem("agentnest.push.owner")).toBe(USER);
  });
});
