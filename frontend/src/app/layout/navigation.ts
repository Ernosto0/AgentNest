import type { ComponentType, SVGProps } from "react";
import { HomeIcon, ImageIcon, InboxIcon, MenuIcon, ShieldCheckIcon } from "@/components/icons";

export interface NavItem {
  /** Path relative to /w/:workspaceId ("" is the home route). */
  path: string;
  /** Catalog key of the label. */
  labelKey: "nav.home" | "nav.inbox" | "nav.content" | "nav.approvals" | "nav.more";
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

// Bottom tabs on mobile, sidebar on desktop (user-journeys.md §1).
export const NAV_ITEMS: readonly NavItem[] = [
  { path: "", labelKey: "nav.home", icon: HomeIcon },
  { path: "inbox", labelKey: "nav.inbox", icon: InboxIcon },
  { path: "content", labelKey: "nav.content", icon: ImageIcon },
  { path: "approvals", labelKey: "nav.approvals", icon: ShieldCheckIcon },
  { path: "more", labelKey: "nav.more", icon: MenuIcon },
];
