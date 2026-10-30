import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { matchRoutes } from "react-router-dom";
import { appRoutes } from "@/app/router";
import type { Role } from "@/api/types";
import { ME, WS_GOLKENT, WS_HARBOR, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { selectedDestination, workspaceSwitchTarget } from "./navigation";

afterEach(() => vi.unstubAllGlobals());
const base = `/w/${WS_GOLKENT}`;
const other = `/w/${WS_HARBOR}`;
function routes(role: Role = "owner", demoTools = true) {
  return {
    "GET /api/v1/meta": () => json({ product_name: "AgentNest", demo_tools_enabled: demoTools, llm_mode: "fake" }),
    "GET /api/v1/auth/me": () => json({ ...ME, memberships: ME.memberships.map(member => ({ ...member, role })) }),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET /api/v1/workspaces/${WS_HARBOR}`]: () => json(workspace(WS_HARBOR)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}/conversations`]: () => json({ items: [], next_cursor: null }),
    [`GET /api/v1/workspaces/${WS_HARBOR}/conversations`]: () => json({ items: [], next_cursor: null }),
  };
}

describe("workspace navigation scope", () => {
  it("retains every baseline concrete route and both not-found entry points", () => {
    const existing = ["/login", "/invite/fictional-token", "/", "/workspaces/new", base,
      ...["inbox", "inbox/conversation", "content", "content/content-id", "approvals", "more", "more/settings", "more/settings/connections", "more/settings/members", "more/settings/system-health", "more/knowledge", "more/knowledge/suggestions", "more/knowledge/answers", "more/knowledge/pricing", "more/agent", "more/agent/questions", "more/agent/questions/question", "more/agent/memory/customer", "more/agent/comments", "more/agent/comments/thread", "more/agent/tasks/task", "more/automation", "more/reports", "more/reports/2026-10-30/metric", "more/activity", "more/notifications", "more/dev"].map(path => `${base}/${path}`)];
    expect(existing).toHaveLength(32);
    for (const path of existing) {
      const leaf = matchRoutes(appRoutes, `${path}?account=existing&custom=preserved`)?.at(-1)?.route;
      expect(leaf, path).toBeDefined();
      expect(leaf?.path, path).not.toBe("*");
    }
    expect(matchRoutes(appRoutes, "/missing")?.at(-1)?.route.path).toBe("*");
    expect(matchRoutes(appRoutes, `${base}/missing`)?.at(-1)?.route.path).toBe("*");
  });
  it.each([
    ["inbox/conversation-old", "?account=old&attention=needs_human&cursor=old", "inbox", "?attention=needs_human"],
    ["content/content-old", "?tab=scheduled&status=on_hold&view=agenda&account=old&snapshot=old", "content", "?tab=scheduled&status=on_hold&view=agenda"],
    ["approvals", "?tab=history&approval=old", "approvals", "?tab=history"],
    ["more/agent/questions/question-old", "?account=old", "more/agent/questions", ""],
    ["more/agent/comments/thread-old", "?account=old", "more/agent/comments", ""],
    ["more/agent/memory/customer-old", "?account=old", "more/agent", ""],
    ["more/agent/tasks/task-old", "?account=old", "more/agent", ""],
    ["more/reports/2026-10-30/metric", "?snapshot=old", "more/reports", ""],
    ["more/knowledge/pricing", "?fact=old", "more/knowledge/pricing", ""],
    ["more/settings/connections", "?oauth=old", "more/settings/connections", ""],
    ["unknown/old", "?account=old", "", ""],
  ])("switching from %s keeps only safe list context", (path, search, safe, expectedSearch) => {
    expect(workspaceSwitchTarget(`${base}/${path}`, search, WS_GOLKENT, WS_HARBOR)).toEqual({ pathname: `${other}${safe ? `/${safe}` : ""}`, search: expectedSearch });
  });
  it("selects parent areas without conflating nearby route prefixes", () => {
    expect(selectedDestination("more/knowledge/pricing")).toBe("more/knowledge");
    expect(selectedDestination("more/agent/tasks/task")).toBe("more/agent");
    expect(selectedDestination("inbox/conversation")).toBe("inbox");
    expect(selectedDestination("inbox-unknown")).toBe("more");
  });
  it.each(["owner", "manager", "staff"] as Role[])("offers authorized %s destinations in More and launcher", async role => {
    mockApi(routes(role, false));
    renderApp(`${base}/more`);
    await screen.findByRole("heading", { name: "Daha fazla" });
    const main = within(screen.getByRole("main"));
    expect(main.getByRole("link", { name: "Günlük rapor" })).toBeInTheDocument();
    expect(main.queryByRole("link", { name: "Etkinlik" }) !== null).toBe(role !== "staff");
    expect(main.queryByRole("link", { name: "Sistem durumu" }) !== null).toBe(role !== "staff");
    expect(main.queryByRole("link", { name: "Geliştirici araçları" })).toBeNull();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Gezinme hedeflerini aç" }));
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("link", { name: "Günlük rapor" })).toBeInTheDocument();
    expect(dialog.queryByRole("link", { name: "Etkinlik" }) !== null).toBe(role !== "staff");
    expect(dialog.queryByRole("link", { name: "Geliştirici araçları" })).toBeNull();
  });
  it("filters local destinations, uses keyboard links and restores pointer or shortcut focus", async () => {
    const requests = mockApi(routes());
    const { router } = renderApp(`${base}/more`);
    await screen.findByRole("heading", { name: "Daha fazla" });
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "Gezinme hedeflerini aç" });
    await user.click(trigger);
    const filter = screen.getByRole("textbox", { name: "Hedefleri filtrele" });
    expect(filter).toHaveFocus();
    await user.type(filter, "İŞLETME");
    expect(within(screen.getByRole("dialog")).getAllByRole("link")).toHaveLength(1);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
    const switcher = screen.getByRole("combobox", { name: "Çalışma alanı" });
    switcher.focus();
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("textbox", { name: "Hedefleri filtrele" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(switcher).toHaveFocus();
    await user.click(trigger);
    await user.type(screen.getByRole("textbox", { name: "Hedefleri filtrele" }), "Gelen");
    await user.keyboard("{ArrowDown}{Enter}");
    await waitFor(() => expect(router.state.location.pathname).toBe(`${base}/inbox`));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(requests.every(request => request.method === "GET")).toBe(true);
    expect(requests.some(request => request.path.includes("commands"))).toBe(false);
  });
  it("preserves direct query state and browser history, then clears cross-workspace record identifiers", async () => {
    mockApi(routes());
    const { router } = renderApp(`${base}/inbox?attention=needs_human&account=old&custom=keep`);
    await screen.findByRole("heading", { name: "Gelen kutusu" });
    expect(router.state.location.search).toBe("?attention=needs_human&account=old&custom=keep");
    await act(() => router.navigate(`${base}/more`));
    await act(() => router.navigate(-1));
    expect(router.state.location.search).toBe("?attention=needs_human&account=old&custom=keep");
    await userEvent.setup().selectOptions(screen.getByRole("combobox", { name: "Çalışma alanı" }), WS_HARBOR);
    await waitFor(() => expect(router.state.location.pathname).toBe(`${other}/inbox`));
    expect(router.state.location.search).toBe("?attention=needs_human");
  });
  it("clears the shell when the current membership is removed", async () => {
    let revoked = false;
    mockApi({ ...routes(), "GET /api/v1/auth/me": () => json({ ...ME, memberships: revoked ? [] : ME.memberships }) });
    const { client } = renderApp(`${base}/more`);
    await screen.findByRole("heading", { name: "Daha fazla" });
    revoked = true;
    await act(() => client.refetchQueries({ queryKey: ["me"] }));
    expect(await screen.findByRole("heading", { name: "Bulunamadı" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Ana gezinme" })).toBeNull();
  });
  it("foreign/deleted workspaces remain indistinguishable", async () => {
    mockApi({ ...routes(), [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => problem(404, "NOT_FOUND") });
    renderApp(`${base}/more`);
    expect(await screen.findByRole("heading", { name: "Bulunamadı" })).toBeInTheDocument();
    expect(screen.queryByTestId("desktop-sidebar")).toBeNull();
  });
});
