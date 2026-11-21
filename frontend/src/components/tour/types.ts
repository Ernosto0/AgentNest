export type TourId = "home" | "inbox" | "content" | "approvals" | "knowledge";

export interface TourStepDef {
  selector: string;
  titleKey: string;
  descriptionKey: string;
  side?: "top" | "right" | "bottom" | "left";
}
