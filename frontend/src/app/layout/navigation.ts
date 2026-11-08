import type { ComponentType, SVGProps } from "react";
import type { Role } from "@/api/types";
import { HomeIcon, ImageIcon, InboxIcon, MenuIcon, ShieldCheckIcon, BellIcon, ClockIcon, BookIcon, ChartIcon, SettingsIcon, SparkIcon, UsersIcon, LinkIcon, InfoIcon } from "@/components/icons";

export interface NavItem {
  /** Path relative to /w/:workspaceId ("" is the home route). */
  path: string;
  /** Catalog key of the label. */
  labelKey: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  managementOnly?: boolean;
  demoOnly?: boolean;
}

// Bottom tabs on mobile, sidebar on desktop (user-journeys.md §1).
export const NAV_ITEMS: readonly NavItem[] = [
  { path: "", labelKey: "nav.home", icon: HomeIcon },
  { path: "inbox", labelKey: "nav.inbox", icon: InboxIcon },
  { path: "content", labelKey: "nav.content", icon: ImageIcon },
  { path: "approvals", labelKey: "nav.approvals", icon: ShieldCheckIcon },
  { path: "more", labelKey: "nav.more", icon: MenuIcon },
];

export const DESTINATION_GROUPS: readonly { labelKey: string; items: readonly NavItem[] }[] = [
  { labelKey: "shell.daily", items: NAV_ITEMS.slice(0, 4) },
  { labelKey: "shell.business", items: [
    { path: "more/agent", labelKey: "shell.assistant", icon: SparkIcon },
    { path: "more/knowledge", labelKey: "more.knowledge", icon: BookIcon },
    { path: "more/reports", labelKey: "more.reports", icon: ChartIcon },
  ] },
  { labelKey: "shell.workspace", items: [
    { path: "more/settings/connections", labelKey: "more.connections", icon: LinkIcon },
    { path: "more/activity", labelKey: "more.activity", icon: ClockIcon, managementOnly: true },
    { path: "more/settings", labelKey: "more.settings", icon: SettingsIcon },
  ] },
];

export const MORE_GROUPS: readonly { labelKey: string; items: readonly NavItem[] }[] = [
  { labelKey: "shell.business", items: [
    ...(DESTINATION_GROUPS[1]?.items ?? []),
    { path: "more/knowledge/answers", labelKey: "more.answers", icon: BookIcon },
    { path: "more/automation", labelKey: "more.automation", icon: ShieldCheckIcon },
  ] },
  { labelKey: "shell.workspace", items: [
    ...(DESTINATION_GROUPS[2]?.items ?? []),
    { path: "more/notifications", labelKey: "more.notifications", icon: BellIcon },
    { path: "more/settings/members", labelKey: "more.members", icon: UsersIcon },
    { path: "more/settings/system-health", labelKey: "more.systemHealth", icon: InfoIcon, managementOnly: true },
    { path: "more/dev", labelKey: "more.devPanel", icon: SettingsIcon, demoOnly: true },
  ] },
];

export const allowedDestination = (item: NavItem, role: Role, demoTools: boolean) =>
  (!item.managementOnly || role !== "staff") && (!item.demoOnly || demoTools);
export const workspaceTarget = (workspaceId: string, path: string) => `/w/${workspaceId}${path ? `/${path}` : ""}`;

/** One selected desktop area even for nested record and settings/category URLs. */
export function selectedDestination(path: string): string {
  if (!path) return "";
  if (/^more\/agent\/(questions|comments)(\/|$)/.test(path)) return "inbox";
  if (path === "inbox" || path.startsWith("inbox/")) return "inbox";
  if (path === "content" || path.startsWith("content/")) return "content";
  if (path === "approvals") return "approvals";
  for (const candidate of ["more/agent", "more/knowledge", "more/reports", "more/settings/connections", "more/settings", "more/activity", "more/notifications"]) {
    if (path === candidate || path.startsWith(`${candidate}/`)) return candidate;
  }
  return "more";
}

export function shellContext(path: string): { parent?: string; labelKey: string; width: "wide" | "reading" } {
  const area = selectedDestination(path);
  const item = DESTINATION_GROUPS.flatMap(group => group.items).find(item => item.path === area);
  let labelKey = item?.labelKey ?? "nav.more";
  if (path.startsWith("more/agent/questions")) labelKey = "shell.questions";
  else if (path.startsWith("more/agent/comments")) labelKey = "shell.comments";
  else if (path.startsWith("more/agent/memory/")) labelKey = "shell.memory";
  else if (path.startsWith("more/agent/tasks/")) labelKey = "shell.task";
  else if (path === "more/automation") labelKey = "more.automation";
  else if (path === "more/dev") labelKey = "more.devPanel";
  else if (path.startsWith("more/settings/")) labelKey = MORE_GROUPS.flatMap(group => group.items).find(item => item.path === path)?.labelKey ?? labelKey;
  return { parent: path !== area ? area : undefined, labelKey, width: path.startsWith("more/settings") || path === "more/automation" ? "reading" : "wide" };
}

/** Keep only section/list context; resource/account/snapshot IDs never cross tenants. */
export function workspaceSwitchTarget(pathname: string, search: string, currentId: string, nextId: string) {
  const prefix = `/w/${currentId}`;
  const path = pathname === prefix ? "" : pathname.startsWith(`${prefix}/`) ? pathname.slice(prefix.length + 1) : "";
  let safe = "";
  if (path === "inbox" || path.startsWith("inbox/")) safe = "inbox";
  else if (path === "content" || path.startsWith("content/")) safe = "content";
  else if (path === "approvals") safe = "approvals";
  else if (path.startsWith("more/agent/questions")) safe = "more/agent/questions";
  else if (path.startsWith("more/agent/comments")) safe = "more/agent/comments";
  else if (path.startsWith("more/agent/")) safe = "more/agent";
  else if (path.startsWith("more/reports/")) safe = "more/reports";
  else if (MORE_GROUPS.flatMap(group => group.items).some(item => item.path === path) || path === "more" || path === "more/knowledge/suggestions") safe = path;
  else if (/^more\/knowledge\/(identity|contact|location|hours|service|pricing|promotion|booking|policy|schedule|faq|brand|escalation|custom)$/.test(path)) safe = path;
  const before = new URLSearchParams(search);
  const after = new URLSearchParams();
  const filters: Record<string, readonly string[]> = { content: ["tab", "status", "view"], inbox: ["attention", "section"], approvals: ["tab"], "more/notifications": ["filter"], "more/activity": ["group", "date"], "more/agent": ["panel"] };
  for (const key of filters[safe] ?? []) {
    const value = before.get(key);
    if (value !== null) after.set(key, value);
  }
  return { pathname: workspaceTarget(nextId, safe), search: after.size ? `?${after}` : "" };
}
