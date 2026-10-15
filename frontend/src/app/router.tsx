import { createBrowserRouter, createMemoryRouter, type RouteObject } from "react-router-dom";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { HomePage } from "@/features/home/HomePage";
import { SectionPlaceholderPage } from "@/features/home/SectionPlaceholderPage";
import { MorePage } from "@/features/settings/MorePage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { WorkspaceGate } from "@/features/workspaces/WorkspaceGate";
import { WorkspacePickerPage } from "@/features/workspaces/WorkspacePickerPage";
import { NotFoundPage } from "./NotFoundPage";

export const appRoutes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/", element: <WorkspacePickerPage /> },
      {
        path: "/w/:workspaceId",
        element: <WorkspaceGate />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "inbox", element: <SectionPlaceholderPage section="inbox" /> },
          { path: "content", element: <SectionPlaceholderPage section="content" /> },
          { path: "approvals", element: <SectionPlaceholderPage section="approvals" /> },
          { path: "more", element: <MorePage /> },
          { path: "more/settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];

export const createAppRouter = () => createBrowserRouter(appRoutes);
export const createTestRouter = (initialEntries: string[]) =>
  createMemoryRouter(appRoutes, { initialEntries });
