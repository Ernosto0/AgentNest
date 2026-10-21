import { createBrowserRouter, createMemoryRouter, type RouteObject } from "react-router-dom";
import { NotificationCenter } from "@/features/notifications/NotificationCenter";
import { ActivityFeed } from "@/features/activity/ActivityFeed";
import { ApprovalsList } from "@/features/approvals/ApprovalsList";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { ContentDetailPage } from "@/features/content/ContentDetailPage";
import { ContentPage } from "@/features/content/ContentPage";
import { HomePage } from "@/features/home/HomePage";
import { DevPanel } from "@/features/dev/DevPanel";
import { ConversationPage } from "@/features/inbox/ConversationPage";
import { InboxPage } from "@/features/inbox/InboxPage";
import { ApprovedAnswers } from "@/features/knowledge/ApprovedAnswers";
import { CategoryPage } from "@/features/knowledge/CategoryPage";
import { KnowledgePage } from "@/features/knowledge/KnowledgePage";
import { SuggestionsPage } from "@/features/knowledge/SuggestionsPage";
import { DailyReport } from "@/features/reports/DailyReport";
import { MetricItems } from "@/features/reports/MetricItems";
import { CreateWorkspaceWizard } from "@/features/workspaces/CreateWorkspaceWizard";
import { AutomationSettings } from "@/features/settings/AutomationSettings";
import { Connections } from "@/features/settings/Connections";
import { MorePage } from "@/features/settings/MorePage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { SystemHealth } from "@/features/settings/SystemHealth";
import { WorkspaceGate } from "@/features/workspaces/WorkspaceGate";
import { WorkspacePickerPage } from "@/features/workspaces/WorkspacePickerPage";
import { NotFoundPage } from "./NotFoundPage";

export const appRoutes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/", element: <WorkspacePickerPage /> },
      { path: "/workspaces/new", element: <CreateWorkspaceWizard /> },
      {
        path: "/w/:workspaceId",
        element: <WorkspaceGate />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "inbox", element: <InboxPage /> },
          { path: "inbox/:conversationId", element: <ConversationPage /> },
          { path: "content", element: <ContentPage /> },
          { path: "content/:id", element: <ContentDetailPage /> },
          { path: "approvals", element: <ApprovalsList /> },
          { path: "more", element: <MorePage /> },
          { path: "more/settings", element: <SettingsPage /> },
          { path: "more/settings/connections", element: <Connections /> },
          { path: "more/settings/system-health", element: <SystemHealth /> },
          { path: "more/knowledge", element: <KnowledgePage /> },
          { path: "more/knowledge/suggestions", element: <SuggestionsPage /> },
          { path: "more/knowledge/answers", element: <ApprovedAnswers /> },
          { path: "more/automation", element: <AutomationSettings /> },
          { path: "more/reports", element: <DailyReport /> },
          { path: "more/reports/:date/:key", element: <MetricItems /> },
          { path: "more/activity", element: <ActivityFeed /> },
          { path: "more/notifications", element: <NotificationCenter /> },
          { path: "more/dev", element: <DevPanel /> },
          { path: "more/knowledge/:category", element: <CategoryPage /> },
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
