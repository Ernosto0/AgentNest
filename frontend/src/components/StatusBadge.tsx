import type { ComponentType, SVGProps } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertIcon,
  CalendarIcon,
  CheckIcon,
  ClockIcon,
  HandIcon,
  HourglassIcon,
  MagnifierIcon,
  PauseIcon,
  PencilIcon,
  SpinnerIcon,
} from "./icons";
import { SimulatedBadge } from "./SimulatedBadge";
import type { StatusKey } from "./status";

// The single place that maps server states to labels (user-journeys.md §1, INV-18).
// "Scheduled" is not "published", "approved" is not "sent", and an unknown outcome reads
// "checking": a label never claims more than the server state says.
type Tone = "grey" | "amber" | "orange" | "blue" | "green" | "red";

const TONES: Record<Tone, string> = {
  grey: "bg-slate-100 text-slate-800 ring-slate-300",
  amber: "bg-amber-50 text-amber-900 ring-amber-400",
  orange: "bg-orange-50 text-orange-900 ring-orange-400",
  blue: "bg-blue-50 text-blue-900 ring-blue-400",
  green: "bg-green-50 text-green-900 ring-green-500",
  red: "bg-red-50 text-red-900 ring-red-400",
};

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const PRESENTATION: Record<StatusKey, { tone: Tone; icon: Icon; spins?: boolean }> = {
  draft: { tone: "grey", icon: PencilIcon },
  pending_approval: { tone: "amber", icon: ClockIcon },
  needs_human: { tone: "orange", icon: HandIcon },
  scheduled: { tone: "blue", icon: CalendarIcon },
  on_hold: { tone: "orange", icon: PauseIcon },
  sending: { tone: "blue", icon: SpinnerIcon, spins: true },
  publishing: { tone: "blue", icon: SpinnerIcon, spins: true },
  checking: { tone: "blue", icon: MagnifierIcon },
  sent: { tone: "green", icon: CheckIcon },
  published: { tone: "green", icon: CheckIcon },
  failed: { tone: "red", icon: AlertIcon },
  expired: { tone: "grey", icon: HourglassIcon },
  retry_scheduled: { tone: "blue", icon: ClockIcon },
  rejected: { tone: "red", icon: AlertIcon },
  cancelled: { tone: "grey", icon: PauseIcon },
};

interface StatusBadgeProps {
  status: StatusKey;
  /** Append the SİMÜLASYON / SIMULATED badge (the item came from a mock provider). */
  simulated?: boolean;
  /** Values for labels that carry one (`retry_scheduled` shows `{{time}}`). */
  params?: Record<string, string | number>;
  className?: string;
}

export function StatusBadge({ status, simulated = false, params, className = "" }: StatusBadgeProps) {
  const { t } = useTranslation();
  const { tone, icon: Icon, spins } = PRESENTATION[status];
  return (
    <span className={`inline-flex flex-wrap items-center gap-1.5 ${className}`}>
      <span
        data-status={status}
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium ring-1 ring-inset ${TONES[tone]}`}
      >
        <Icon className={spins ? "motion-safe:animate-spin" : undefined} />
        <span>{t(`status.${status}`, params)}</span>
      </span>
      {simulated ? <SimulatedBadge /> : null}
    </span>
  );
}
