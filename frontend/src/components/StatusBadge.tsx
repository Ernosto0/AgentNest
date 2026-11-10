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
  grey: "bg-surface-subtle text-primary ring-border",
  amber: "bg-attention-subtle text-attention ring-attention",
  orange: "bg-attention-subtle text-attention ring-attention",
  blue: "bg-info-subtle text-info ring-info",
  green: "bg-success-subtle text-success ring-success",
  red: "bg-danger-subtle text-danger ring-danger",
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
  /** Smaller pill for dense surfaces (content cards, agenda); the words stay the same. */
  compact?: boolean;
}

export function StatusBadge({ status, simulated = false, params, className = "", compact = false }: StatusBadgeProps) {
  const { t } = useTranslation();
  const { tone, icon: Icon, spins } = PRESENTATION[status];
  return (
    <span className={`inline-flex flex-wrap items-center gap-1.5 ${className}`}>
      <span
        data-status={status}
        className={`inline-flex items-center rounded-full font-medium ring-1 ring-inset ${
          compact ? "gap-1 px-2 py-px text-xs leading-5" : "gap-1.5 px-2.5 py-1 text-sm"
        } ${TONES[tone]}`}
      >
        <Icon className={`shrink-0 ${spins ? "motion-safe:animate-spin" : ""}`} />
        <span>{t(`status.${status}`, params)}</span>
      </span>
      {simulated ? <SimulatedBadge compact={compact} /> : null}
    </span>
  );
}
