import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import "@/i18n";
import { HomeWelcomePrompt } from "@/features/home/HomeWelcomePrompt";
import { CurrentWorkspaceContext } from "@/features/workspaces/context";
import { workspace } from "@/test/fixtures";
import { PageGuideButton } from "./PageGuideButton";
import { tourIdForPath } from "./tours";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  document.body.innerHTML = "";
});

function renderWithWorkspace(initialEntry: string) {
  return render(
    <CurrentWorkspaceContext.Provider value={{ workspace: workspace("ws_1"), role: "owner" }}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/w/:workspaceId/*" element={<PageGuideButton />} />
        </Routes>
      </MemoryRouter>
    </CurrentWorkspaceContext.Provider>,
  );
}

describe("tourIdForPath", () => {
  it("maps workspace paths to their page tour ids", () => {
    expect(tourIdForPath("")).toBe("home");
    expect(tourIdForPath("inbox")).toBe("inbox");
    expect(tourIdForPath("content")).toBe("content");
    expect(tourIdForPath("approvals")).toBe("approvals");
    expect(tourIdForPath("more/knowledge")).toBe("knowledge");
    expect(tourIdForPath("more/settings")).toBeNull();
  });
});

describe("PageGuideButton", () => {
  it("renders on Home and starts Driver.js with visible targets", async () => {
    const target = document.createElement("div");
    target.setAttribute("data-tour", "home-quick-actions");
    target.getClientRects = () => [{ width: 100, height: 40 } as DOMRect] as unknown as DOMRectList;
    document.body.appendChild(target);

    renderWithWorkspace("/w/ws_1");
    const button = screen.getByTestId("page-guide-button");
    await userEvent.click(button);

    expect(document.querySelector(".driver-popover")).not.toBeNull();
  });

  it.each([
    ["/w/ws_1/inbox", "inbox-tabs"],
    ["/w/ws_1/content", "content-composer"],
    ["/w/ws_1/approvals", "approvals-tabs"],
    ["/w/ws_1/more/knowledge", "knowledge-stats"],
  ])("renders on %s and launches its page tour", async (route, attr) => {
    const target = document.createElement("div");
    target.setAttribute("data-tour", attr);
    target.getClientRects = () => [{ width: 100, height: 40 } as DOMRect] as unknown as DOMRectList;
    document.body.appendChild(target);

    renderWithWorkspace(route);
    await userEvent.click(screen.getByTestId("page-guide-button"));

    expect(document.querySelector(".driver-popover")).not.toBeNull();
  });

  it("does not render on routes without a registered tour", () => {
    renderWithWorkspace("/w/ws_1/more/settings");
    expect(screen.queryByTestId("page-guide-button")).toBeNull();
  });

  it("does not launch while a dialog is open", async () => {
    const target = document.createElement("div");
    target.setAttribute("data-tour", "home-quick-actions");
    target.getClientRects = () => [{ width: 100, height: 40 } as DOMRect] as unknown as DOMRectList;
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    document.body.append(target, dialog);

    renderWithWorkspace("/w/ws_1");
    await userEvent.click(screen.getByTestId("page-guide-button"));

    expect(document.querySelector(".driver-popover")).toBeNull();
  });
});

describe("HomeWelcomePrompt", () => {
  it("persists dismissal per workspace in localStorage", async () => {
    render(<HomeWelcomePrompt workspaceId="ws_1" />);
    expect(screen.getByTestId("home-tour-prompt")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /kapat|dismiss/i }));
    expect(screen.queryByTestId("home-tour-prompt")).toBeNull();
    expect(window.localStorage.getItem("pivoris.tour.homeSeen.ws_1")).toBe("1");
  });

  it("starts the home tour when Start tour is clicked", async () => {
    const target = document.createElement("div");
    target.setAttribute("data-tour", "home-quick-actions");
    target.getClientRects = () => [{ width: 100, height: 40 } as DOMRect] as unknown as DOMRectList;
    document.body.appendChild(target);

    render(<HomeWelcomePrompt workspaceId="ws_1" />);
    await userEvent.click(screen.getByRole("button", { name: /turu başlat|start tour/i }));
    expect(document.querySelector(".driver-popover")).not.toBeNull();
  });
});
