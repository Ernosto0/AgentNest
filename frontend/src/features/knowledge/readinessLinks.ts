import type { Requirement } from "@/api/types";

/**
 * Where a readiness requirement is fixed. Knowledge items link to their category; the account
 * connection and the automation review share one screen.
 */
export function requirementPath(workspaceId: string, link: Requirement["link"]): string | null {
  if (link.target === "integrations" || link.target === "automation") {
    return `/w/${workspaceId}/more/automation`; // the connection and the policies share a screen
  }
  if (link.target !== "knowledge") return null;
  const base = `/w/${workspaceId}/more/knowledge`;
  return link.category ? `${base}/${link.category}` : base;
}
