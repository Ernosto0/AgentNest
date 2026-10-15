import { useTranslation } from "react-i18next";
import { AlertIcon, CheckIcon, ClockIcon, HourglassIcon, PencilIcon, PauseIcon } from "@/components/icons";
import type { ComponentType, SVGProps } from "react";

/** A fact's state as the owner sees it. `missing` is a template item with no fact yet. */
export type ChipState =
  | "verified"
  | "unverified"
  | "contested"
  | "expired"
  | "not_started"
  | "archived"
  | "missing"
  | "present";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const TONES = {
  green: "bg-green-50 text-green-900 ring-green-500",
  amber: "bg-amber-50 text-amber-900 ring-amber-400",
  orange: "bg-orange-50 text-orange-900 ring-orange-400",
  grey: "bg-slate-100 text-slate-800 ring-slate-300",
} as const;

const PRESENTATION: Record<ChipState, { tone: keyof typeof TONES; icon: Icon }> = {
  verified: { tone: "green", icon: CheckIcon },
  present: { tone: "green", icon: CheckIcon },
  unverified: { tone: "amber", icon: ClockIcon },
  contested: { tone: "orange", icon: PauseIcon },
  expired: { tone: "grey", icon: HourglassIcon },
  not_started: { tone: "grey", icon: HourglassIcon },
  archived: { tone: "grey", icon: PencilIcon },
  missing: { tone: "orange", icon: AlertIcon },
};

/** Colour is never the only signal: every state has its own icon and word (WCAG 1.4.1). */
export function FactStatusChip({ state }: { state: ChipState }) {
  const { t } = useTranslation();
  const { tone, icon: Icon } = PRESENTATION[state];
  return (
    <span
      data-state={state}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium whitespace-nowrap ring-1 ring-inset ${TONES[tone]}`}
    >
      <Icon />
      <span>{t(`knowledge.state.${state}`)}</span>
    </span>
  );
}
