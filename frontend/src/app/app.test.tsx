import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, WS_GOLKENT, WS_HARBOR, WS_PRIVATE, workspace } from "@/test/fixtures";
import { json, mockApi, noContent, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const signedIn = {
  "GET /api/v1/meta": () =>
    json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
  "GET /api/v1/auth/me": () => json(ME),
  [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
  [`GET /api/v1/workspaces/${WS_HARBOR}`]: () => json(workspace(WS_HARBOR)),
  [`GET /api/v1/workspaces/${WS_PRIVATE}`]: () => json(workspace(WS_PRIVATE)),
};

describe("auth guard", () => {
  it("sends a visitor without a session to the login screen", async () => {
    mockApi({ ...signedIn, "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED") });
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByRole("heading", { name: "Giriş yap" })).toBeInTheDocument();
  });

  it("logs in with the form and lands on the workspace picker", async () => {
    const user = userEvent.setup();
    let loggedIn = false;
    const requests = mockApi({
      ...signedIn,
      "GET /api/v1/auth/me": () => (loggedIn ? json(ME) : problem(401, "AUTH_REQUIRED")),
      "POST /api/v1/auth/login": () => {
        loggedIn = true;
        return noContent();
      },
    });
    renderApp("/login");

    await user.type(await screen.findByLabelText("E-posta"), "owner@demo.local");
    await user.type(screen.getByLabelText("Parola"), "demo-password");
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));

    expect(await screen.findByRole("heading", { name: "Çalışma alanı seçin" })).toBeInTheDocument();
    const login = requests.find((r) => r.path === "/api/v1/auth/login");
    expect(login?.body).toEqual({ email: "owner@demo.local", password: "demo-password" });
    expect(login?.headers.has("x-csrf-token")).toBe(false); // login is exempt, no session yet
  });

  it("shows a localised, generic message for wrong credentials and keeps the form", async () => {
    const user = userEvent.setup();
    mockApi({
      ...signedIn,
      "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED"),
      "POST /api/v1/auth/login": () => problem(401, "INVALID_CREDENTIALS"),
    });
    renderApp("/login");
    await user.type(await screen.findByLabelText("E-posta"), "owner@demo.local");
    await user.type(screen.getByLabelText("Parola"), "wrong");
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("E-posta veya parola hatalı.");
    expect(alert).toHaveTextContent("İstek kimliği: req-123");
    expect(screen.getByLabelText("E-posta")).toHaveValue("owner@demo.local");
  });

  it("returns to the login screen when the session expires mid-use", async () => {
    let expired = false;
    mockApi({
      ...signedIn,
      "GET /api/v1/auth/me": () => (expired ? problem(401, "AUTH_REQUIRED") : json(ME)),
      [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () =>
        expired ? problem(401, "AUTH_REQUIRED") : json(workspace(WS_GOLKENT)),
    });
    const { client } = renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByRole("heading", { name: "Ana sayfa" })).toBeInTheDocument();

    expired = true;
    await client.refetchQueries({ queryKey: ["workspace", WS_GOLKENT] });
    expect(await screen.findByRole("heading", { name: "Giriş yap" })).toBeInTheDocument();
  });
});

describe("workspace shell", () => {
  it("shows the Turkish shell, the five tabs and the simulation banner on a demo workspace", async () => {
    mockApi(signedIn);
    renderApp(`/w/${WS_GOLKENT}`);

    expect(await screen.findByRole("heading", { name: "Ana sayfa" })).toBeInTheDocument();
    const banner = screen.getByTestId("simulation-banner");
    expect(banner).toHaveTextContent("Demo çalışma alanı — simülasyon");
    expect(banner).toHaveTextContent("gerçek Instagram'a hiçbir şey gönderilmez");

    for (const nav of screen.getAllByRole("navigation", { name: "Ana gezinme" })) {
      for (const label of ["Ana sayfa", "Gelen kutusu", "İçerik", "Onaylar", "Daha fazla"]) {
        expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
      }
    }
    expect(screen.getByText("Bu bölüm bir sonraki aşamada gelecek")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("tr");
  });

  it("shows no simulation banner on a non-demo workspace", async () => {
    mockApi(signedIn);
    renderApp(`/w/${WS_PRIVATE}`);
    expect(await screen.findByRole("heading", { name: "Ana sayfa" })).toBeInTheDocument();
    expect(screen.queryByTestId("simulation-banner")).toBeNull();
    expect(screen.queryByTestId("simulated-badge")).toBeNull();
  });

  it("the content tab shows a localised empty state", async () => {
    mockApi(signedIn);
    renderApp(`/w/${WS_GOLKENT}/content`);
    expect(await screen.findByRole("heading", { name: "İçerik" })).toBeInTheDocument();
    expect(screen.getByText("Bu bölüm bir sonraki aşamada gelecek")).toBeInTheDocument();
  });

  it("the inbox tab is a real screen with its own empty state (Phase 4)", async () => {
    mockApi({
      ...signedIn,
      [`GET /api/v1/workspaces/${WS_GOLKENT}/conversations`]: () => json({ items: [], next_cursor: null }),
    });
    renderApp(`/w/${WS_GOLKENT}/inbox`);
    expect(await screen.findByRole("heading", { name: "Gelen kutusu" })).toBeInTheDocument();
    expect(await screen.findByText("Burada konuşma yok")).toBeInTheDocument();
  });

  it("the approvals tab is a real screen with its own empty state (Phase 3)", async () => {
    mockApi({
      ...signedIn,
      [`GET /api/v1/workspaces/${WS_GOLKENT}/approvals`]: () => json({ items: [], next_cursor: null }),
    });
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    expect(await screen.findByRole("heading", { name: "Onaylar" })).toBeInTheDocument();
    expect(await screen.findByText("Bekleyen onay yok")).toBeInTheDocument();
  });

  it("answers 'not found' for a workspace the user is not a member of", async () => {
    const foreign = "44444444-4444-4444-8444-444444444444";
    mockApi({ ...signedIn, [`GET /api/v1/workspaces/${foreign}`]: () => problem(404, "NOT_FOUND") });
    renderApp(`/w/${foreign}`);
    expect(await screen.findByRole("heading", { name: "Bulunamadı" })).toBeInTheDocument();
    expect(screen.queryByTestId("simulation-banner")).toBeNull();
    expect(screen.getByRole("link", { name: "Çalışma alanlarıma dön" })).toHaveAttribute("href", "/");
  });

  it("switches workspace from the header and keeps the current section", async () => {
    const user = userEvent.setup();
    mockApi(signedIn);
    const { router } = renderApp(`/w/${WS_GOLKENT}/inbox`);
    await screen.findByRole("heading", { name: "Gelen kutusu" });

    await user.selectOptions(screen.getByLabelText("Çalışma alanı"), WS_HARBOR);

    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${WS_HARBOR}/inbox`));
    expect(await screen.findByRole("heading", { name: "Gelen kutusu" })).toBeInTheDocument();
  });
});

describe("workspace picker", () => {
  it("lists exactly the memberships the API returned, with roles and demo badges", async () => {
    mockApi({
      ...signedIn,
      "GET /api/v1/auth/me": () => json({ ...ME, memberships: [ME.memberships[0]] }),
    });
    renderApp("/");
    const list = await screen.findByRole("list");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent("Gölkent Fitness");
    expect(items[0]).toHaveTextContent("Sahip");
    expect(within(items[0]!).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(items[0]!).getByRole("link")).toHaveAttribute("href", `/w/${WS_GOLKENT}`);
  });
});

describe("language", () => {
  it("More → Settings → Language switches every string and saves it on the account", async () => {
    const user = userEvent.setup();
    const requests = mockApi({
      ...signedIn,
      "PATCH /api/v1/auth/me": (r: RecordedRequest) =>
        json({ ...ME, user: { ...ME.user, ui_locale: (r.body as { ui_locale: "tr" | "en" }).ui_locale } }),
    });
    renderApp(`/w/${WS_GOLKENT}`);
    await screen.findByRole("heading", { name: "Ana sayfa" });

    await user.click(within(screen.getAllByRole("navigation")[1]!).getByRole("link", { name: "Daha fazla" }));
    await user.click(await screen.findByRole("link", { name: "Ayarlar" }));
    expect(await screen.findByRole("heading", { name: "Dil" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(await screen.findByRole("heading", { name: "Language" })).toBeInTheDocument();
    expect(screen.getByTestId("simulation-banner")).toHaveTextContent("Demo workspace — simulation");
    for (const nav of screen.getAllByRole("navigation", { name: "Main navigation" })) {
      expect(within(nav).getByRole("link", { name: "Inbox" })).toBeInTheDocument();
      expect(within(nav).queryByRole("link", { name: "Gelen kutusu" })).toBeNull();
    }
    expect(document.documentElement.lang).toBe("en");

    const patch = requests.find((r) => r.method === "PATCH");
    expect(patch?.body).toEqual({ ui_locale: "en" });
    expect(patch?.headers.get("x-csrf-token")).toBe(ME.csrf_token); // state-changing: CSRF sent
    expect(patch?.headers.get("accept-language")).toBe("en");
  });

  it("uses the account language over the device default after sign-in", async () => {
    mockApi({
      ...signedIn,
      "GET /api/v1/auth/me": () => json({ ...ME, user: { ...ME.user, ui_locale: "en" } }),
    });
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  });
});

describe("sign out", () => {
  it("calls the API with the CSRF token, clears the session and returns to login", async () => {
    const user = userEvent.setup();
    let signedOut = false;
    const requests = mockApi({
      ...signedIn,
      "GET /api/v1/auth/me": () => (signedOut ? problem(401, "AUTH_REQUIRED") : json(ME)),
      "POST /api/v1/auth/logout": () => {
        signedOut = true;
        return noContent();
      },
    });
    renderApp(`/w/${WS_GOLKENT}/more`);
    await user.click(await screen.findByRole("button", { name: "Çıkış yap" }));

    expect(await screen.findByRole("heading", { name: "Giriş yap" })).toBeInTheDocument();
    const logout = requests.find((r) => r.path === "/api/v1/auth/logout");
    expect(logout?.headers.get("x-csrf-token")).toBe(ME.csrf_token);
  });
});
