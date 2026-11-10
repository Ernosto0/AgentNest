import type { ComponentType, SVGProps } from "react";
import type { FactCategory } from "@/api/types";
import {
  AlertIcon,
  CalendarIcon,
  ChatIcon,
  CheckIcon,
  ClockIcon,
  HandIcon,
  HourglassIcon,
  LayersIcon,
  ListIcon,
  MapPinIcon,
  NoteIcon,
  PauseIcon,
  PencilIcon,
  PercentIcon,
  PhoneIcon,
  PlusIcon,
  QuestionIcon,
  ShieldCheckIcon,
  StoreIcon,
  TagIcon,
} from "@/components/icons";

export type Icon = ComponentType<SVGProps<SVGSVGElement>>;

/**
 * A fact's state as the owner sees it. `missing`, `needed` and `not_added` describe a template
 * item with no fact yet: `needed` blocks setup, `not_added` is optional.
 */
export type ChipState =
  | "verified"
  | "unverified"
  | "contested"
  | "expired"
  | "not_started"
  | "archived"
  | "missing"
  | "present"
  | "needed"
  | "one_of"
  | "not_added";

export type StatusTone = "success" | "attention" | "neutral";

/** Pill colours per tone. Text colour alone is never the signal: each state has an icon and a word. */
export const TONE_PILL: Record<StatusTone, string> = {
  success: "bg-success-subtle text-success",
  attention: "bg-attention-subtle text-attention",
  neutral: "bg-surface-subtle text-secondary",
};

export const TONE_TEXT: Record<StatusTone, string> = {
  success: "text-success",
  attention: "text-attention",
  neutral: "text-secondary",
};

export const STATE_PRESENTATION: Record<ChipState, { tone: StatusTone; icon: Icon }> = {
  verified: { tone: "success", icon: CheckIcon },
  present: { tone: "success", icon: CheckIcon },
  unverified: { tone: "attention", icon: ClockIcon },
  contested: { tone: "attention", icon: PauseIcon },
  needed: { tone: "attention", icon: AlertIcon },
  one_of: { tone: "attention", icon: AlertIcon },
  missing: { tone: "attention", icon: AlertIcon },
  expired: { tone: "neutral", icon: HourglassIcon },
  not_started: { tone: "neutral", icon: CalendarIcon },
  archived: { tone: "neutral", icon: PencilIcon },
  not_added: { tone: "neutral", icon: PlusIcon },
};

export const CATEGORY_ICON: Record<FactCategory, Icon> = {
  identity: StoreIcon,
  contact: PhoneIcon,
  location: MapPinIcon,
  hours: ClockIcon,
  service: LayersIcon,
  pricing: TagIcon,
  promotion: PercentIcon,
  booking: CalendarIcon,
  policy: ShieldCheckIcon,
  schedule: ListIcon,
  faq: QuestionIcon,
  brand: ChatIcon,
  escalation: HandIcon,
  custom: NoteIcon,
};

