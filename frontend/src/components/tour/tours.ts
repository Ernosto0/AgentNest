import { selectedDestination } from "@/app/layout/navigation";
import type { TourId, TourStepDef } from "./types";

export const TOURS: Partial<Record<TourId, readonly TourStepDef[]>> = {
  home: [
    {
      selector: '[data-tour="home-quick-actions"]',
      titleKey: "home.tour.quickActionsTitle",
      descriptionKey: "home.tour.quickActionsDesc",
      side: "bottom",
    },
    {
      selector: '[data-tour="home-attention"]',
      titleKey: "home.tour.attentionTitle",
      descriptionKey: "home.tour.attentionDesc",
      side: "left",
    },
    {
      selector: '[data-tour="home-assistant"]',
      titleKey: "home.tour.assistantTitle",
      descriptionKey: "home.tour.assistantDesc",
      side: "top",
    },
    {
      selector: '[data-tour="home-upcoming"]',
      titleKey: "home.tour.upcomingTitle",
      descriptionKey: "home.tour.upcomingDesc",
      side: "top",
    },
  ],
  inbox: [
    {
      selector: '[data-tour="inbox-tabs"]',
      titleKey: "convo.tour.tabsTitle",
      descriptionKey: "convo.tour.tabsDesc",
      side: "bottom",
    },
    {
      selector: '[data-tour="inbox-list"]',
      titleKey: "convo.tour.listTitle",
      descriptionKey: "convo.tour.listDesc",
      side: "right",
    },
    {
      selector: '[data-tour="inbox-detail"]',
      titleKey: "convo.tour.detailTitle",
      descriptionKey: "convo.tour.detailDesc",
      side: "left",
    },
  ],
  content: [
    {
      selector: '[data-tour="content-composer"]',
      titleKey: "content.tour.composerTitle",
      descriptionKey: "content.tour.composerDesc",
      side: "bottom",
    },
    {
      selector: '[data-tour="content-views"]',
      titleKey: "content.tour.viewsTitle",
      descriptionKey: "content.tour.viewsDesc",
      side: "bottom",
    },
    {
      selector: '[data-tour="content-tabs"]',
      titleKey: "content.tour.tabsTitle",
      descriptionKey: "content.tour.tabsDesc",
      side: "top",
    },
  ],
  approvals: [
    {
      selector: '[data-tour="approvals-tabs"]',
      titleKey: "approvals.tour.tabsTitle",
      descriptionKey: "approvals.tour.tabsDesc",
      side: "bottom",
    },
    {
      selector: '[data-tour="approvals-list"]',
      titleKey: "approvals.tour.listTitle",
      descriptionKey: "approvals.tour.listDesc",
      side: "top",
    },
  ],
  knowledge: [
    {
      selector: '[data-tour="knowledge-stats"]',
      titleKey: "knowledge.tour.statsTitle",
      descriptionKey: "knowledge.tour.statsDesc",
      side: "bottom",
    },
    {
      selector: '[data-tour="knowledge-teach"]',
      titleKey: "knowledge.tour.teachTitle",
      descriptionKey: "knowledge.tour.teachDesc",
      side: "left",
    },
    {
      selector: '[data-tour="knowledge-categories"]',
      titleKey: "knowledge.tour.categoriesTitle",
      descriptionKey: "knowledge.tour.categoriesDesc",
      side: "top",
    },
  ],
};

/** Resolve the active page tour from a workspace-relative path. */
export function tourIdForPath(path: string): TourId | null {
  const area = selectedDestination(path);
  if (area === "") return "home";
  if (area === "inbox") return "inbox";
  if (area === "content") return "content";
  if (area === "approvals") return "approvals";
  if (area === "more/knowledge") return "knowledge";
  return null;
}
