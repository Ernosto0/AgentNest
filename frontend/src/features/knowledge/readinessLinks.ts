import type { Requirement } from "@/api/types";

/**
 * Where a readiness requirement is fixed. Knowledge items link to their category; account
 * connection and automation review have no screen before Phase 4, so they have no link yet.
 */
export function requirementPath(workspaceId: string, link: Requirement["link"]): string | null {
  if (link.target !== "knowledge") return null;
  const base = `/w/${workspaceId}/more/knowledge`;
  return link.category ? `${base}/${link.category}` : base;
}
