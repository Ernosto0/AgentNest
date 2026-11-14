import { lazy, Suspense, type ComponentType, type ReactElement } from "react";
import { InboxWorkspace } from "@/features/inbox/InboxWorkspace";
import { createBrowserRouter, createMemoryRouter, type RouteObject } from "react-router-dom";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { WorkspaceGate } from "@/features/workspaces/WorkspaceGate";

const routePreloaders: Array<() => Promise<unknown>> = [];

function lazyNamed<T extends Record<string, ComponentType<any>>>(
  loader: () => Promise<T>,
  name: keyof T,
) {
  let Resolved: ComponentType<any> | null = null;
  const load = async () => {
    const mod = await loader();
    const Component = mod[name]!;
    Resolved = Component;
    return { default: Component };
  };
  routePreloaders.push(load);
  const Lazy = lazy(load);
  return function LazyRoute(props: any) {
    if (Resolved) {
      const Comp = Resolved;
      return <Comp {...props} />;
    }
    return <Lazy {...props} />;
  };
}

export async function preloadRoutes(): Promise<void> {
  await Promise.all(routePreloaders.map((load) => load()));
}

function wrapLazy(element: ReactElement) {
  return <Suspense fallback={null}>{element}</Suspense>;
}

const QuestionPage = lazyNamed(() => import("@/features/agent-work/WorkPages"), "QuestionPage");
const MemoryPage = lazyNamed(() => import("@/features/agent-work/WorkPages"), "MemoryPage");
const CommentThreadPage = lazyNamed(
  () => import("@/features/agent-work/WorkPages"),
  "CommentThreadPage",
);
const TaskPage = lazyNamed(() => import("@/features/agent-work/WorkPages"), "TaskPage");
const AgentPage = lazyNamed(() => import("@/features/agent/AgentPage"), "AgentPage");
const NotificationCenter = lazyNamed(
  () => import("@/features/notifications/NotificationCenter"),
  "NotificationCenter",
);
const ActivityFeed = lazyNamed(() => import("@/features/activity/ActivityFeed"), "ActivityFeed");
const ApprovalsList = lazyNamed(
  () => import("@/features/approvals/ApprovalsList"),
  "ApprovalsList",
);
const LoginPage = lazyNamed(() => import("@/features/auth/LoginPage"), "LoginPage");
const ResetPasswordPage = lazyNamed(
  () => import("@/features/auth/ResetPasswordPage"),
  "ResetPasswordPage",
);
const ContentDetailPage = lazyNamed(
  () => import("@/features/content/ContentDetailPage"),
  "ContentDetailPage",
);
const ContentPage = lazyNamed(() => import("@/features/content/ContentPage"), "ContentPage");
const HomePage = lazyNamed(() => import("@/features/home/HomePage"), "HomePage");
const DevPanel = lazyNamed(() => import("@/features/dev/DevPanel"), "DevPanel");
const AcceptInvite = lazyNamed(() => import("@/features/invites/AcceptInvite"), "AcceptInvite");
const ConversationPage = lazyNamed(
  () => import("@/features/inbox/ConversationPage"),
  "ConversationPage",
);
const InboxPage = lazyNamed(() => import("@/features/inbox/InboxPage"), "InboxPage");
const ApprovedAnswers = lazyNamed(
  () => import("@/features/knowledge/ApprovedAnswers"),
  "ApprovedAnswers",
);
const CategoryPage = lazyNamed(() => import("@/features/knowledge/CategoryPage"), "CategoryPage");
const KnowledgePage = lazyNamed(
  () => import("@/features/knowledge/KnowledgePage"),
  "KnowledgePage",
);
const SuggestionsPage = lazyNamed(
  () => import("@/features/knowledge/SuggestionsPage"),
  "SuggestionsPage",
);
const DailyReport = lazyNamed(() => import("@/features/reports/DailyReport"), "DailyReport");
const MetricItems = lazyNamed(() => import("@/features/reports/MetricItems"), "MetricItems");
const CreateWorkspaceWizard = lazyNamed(
  () => import("@/features/workspaces/CreateWorkspaceWizard"),
  "CreateWorkspaceWizard",
);
const AutomationSettings = lazyNamed(
  () => import("@/features/settings/AutomationSettings"),
  "AutomationSettings",
);
const Connections = lazyNamed(() => import("@/features/settings/Connections"), "Connections");
const Members = lazyNamed(() => import("@/features/settings/Members"), "Members");
const MorePage = lazyNamed(() => import("@/features/settings/MorePage"), "MorePage");
const SettingsPage = lazyNamed(() => import("@/features/settings/SettingsPage"), "SettingsPage");
const SystemHealth = lazyNamed(() => import("@/features/settings/SystemHealth"), "SystemHealth");
const WorkspacePickerPage = lazyNamed(
  () => import("@/features/workspaces/WorkspacePickerPage"),
  "WorkspacePickerPage",
);
const PrivacyPolicyPage = lazyNamed(
  () => import("@/features/legal/PrivacyPolicyPage"),
  "PrivacyPolicyPage",
);
const DataDeletionInfoPage = lazyNamed(
  () => import("@/features/legal/DataDeletionInfoPage"),
  "DataDeletionInfoPage",
);
const NotFoundPage = lazyNamed(() => import("./NotFoundPage"), "NotFoundPage");

export const appRoutes: RouteObject[] = [
  { path: "/login", element: wrapLazy(<LoginPage />) },
  { path: "/privacy", element: wrapLazy(<PrivacyPolicyPage />) },
  { path: "/data-deletion", element: wrapLazy(<DataDeletionInfoPage />) },
  { path: "/reset-password", element: wrapLazy(<ResetPasswordPage />) },
  { path: "/reset-password/:token", element: wrapLazy(<ResetPasswordPage />) },
  { path: "/invite/:token", element: wrapLazy(<AcceptInvite />) },
  {
    element: <RequireAuth />,
    children: [
      { path: "/", element: wrapLazy(<WorkspacePickerPage />) },
      { path: "/workspaces/new", element: wrapLazy(<CreateWorkspaceWizard />) },
      {
        path: "/w/:workspaceId",
        element: <WorkspaceGate />,
        children: [
          { index: true, element: wrapLazy(<HomePage />) },
          { element: <InboxWorkspace />, children: [
            { path: "inbox", element: wrapLazy(<InboxPage />) },
            { path: "inbox/:conversationId", element: wrapLazy(<ConversationPage />) },
            { path: "more/agent/questions", element: wrapLazy(<InboxPage />) },
            { path: "more/agent/questions/:questionId", element: wrapLazy(<QuestionPage />) },
            { path: "more/agent/comments", element: wrapLazy(<InboxPage />) },
            { path: "more/agent/comments/:threadId", element: wrapLazy(<CommentThreadPage />) },
          ] },
          { path: "more/agent/memory/:customerId", element: wrapLazy(<MemoryPage />) },
          { path: "more/agent/tasks/:taskId", element: wrapLazy(<TaskPage />) },
          { path: "content", element: wrapLazy(<ContentPage />) },
          { path: "content/:id", element: wrapLazy(<ContentDetailPage />) },
          { path: "approvals", element: wrapLazy(<ApprovalsList />) },
          { path: "more", element: wrapLazy(<MorePage />) },
          { path: "more/settings", element: wrapLazy(<SettingsPage />) },
          { path: "more/settings/connections", element: wrapLazy(<Connections />) },
          { path: "more/settings/members", element: wrapLazy(<Members />) },
          { path: "more/settings/system-health", element: wrapLazy(<SystemHealth />) },
          { path: "more/knowledge", element: wrapLazy(<KnowledgePage />) },
          { path: "more/knowledge/suggestions", element: wrapLazy(<SuggestionsPage />) },
          { path: "more/knowledge/answers", element: wrapLazy(<ApprovedAnswers />) },
          { path: "more/agent", element: wrapLazy(<AgentPage />) },
          { path: "more/automation", element: wrapLazy(<AutomationSettings />) },
          { path: "more/reports", element: wrapLazy(<DailyReport />) },
          { path: "more/reports/:date/:key", element: wrapLazy(<MetricItems />) },
          { path: "more/activity", element: wrapLazy(<ActivityFeed />) },
          { path: "more/notifications", element: wrapLazy(<NotificationCenter />) },
          { path: "more/dev", element: wrapLazy(<DevPanel />) },
          { path: "more/knowledge/:category", element: wrapLazy(<CategoryPage />) },
          { path: "*", element: wrapLazy(<NotFoundPage embedded />) },
        ],
      },
    ],
  },
  { path: "*", element: wrapLazy(<NotFoundPage />) },
];

export const createAppRouter = () => createBrowserRouter(appRoutes);
export const createTestRouter = (initialEntries: string[]) =>
  createMemoryRouter(appRoutes, { initialEntries });
