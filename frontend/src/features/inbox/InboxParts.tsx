import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { Conversation, SocialAccount } from "@/api/types";
import { AlertIcon, ChevronDownIcon, HandIcon, InfoIcon, SparkIcon } from "@/components/icons";
import { daysAgo, dayKey, initials } from "./labels";

/** Shared focus ring (matches the Today dashboard). */
export const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

/** A working surface of the inbox: white with a hairline, like the Today panels. */
export const PANE = "min-w-0 rounded-2xl border border-border bg-surface";

/** A customer's initials in a calm sage circle. Decorative: the name is always next to it. */
export function CustomerAvatar({ label, size = "md", selected = false }: { label: string; size?: "md" | "lg"; selected?: boolean }) {
  const dims = size === "lg" ? "size-11 text-sm" : "size-10 text-xs";
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-full font-bold tracking-tight transition-colors ${dims} ${
        selected ? "bg-action text-on-action" : "bg-assistant text-action"
      }`}
    >
      {initials(label)}
    </span>
  );
}

const ATTENTION: Record<Exclude<Conversation["attention"], "none">, { tone: string; icon: ReactNode }> = {
  // The assistant has prepared a reply: the assistant's own tone, not an alarm.
  needs_approval: { tone: "bg-assistant text-action", icon: <SparkIcon /> },
  needs_human: { tone: "bg-attention-subtle text-attention", icon: <HandIcon /> },
  failed: { tone: "bg-danger-subtle text-danger", icon: <AlertIcon /> },
};

/** Why a conversation waits for you. Each reason has its own tone and icon; the word carries the meaning. */
export function AttentionChip({ attention, sample = false }: { attention: Conversation["attention"]; /** An explanatory example, not a conversation's state. */ sample?: boolean }) {
  const { t } = useTranslation();
  if (attention === "none") return null;
  const { tone, icon } = ATTENTION[attention];
  return (
    <span
      data-testid={sample ? undefined : "attention-chip"}
      className={`inline-flex min-w-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs leading-4 font-semibold ${tone}`}
    >
      <span aria-hidden="true" className="shrink-0 text-[0.8125rem]">{icon}</span>
      {t(`convo.attention.${attention}`)}
    </span>
  );
}

/** A quiet neutral pill for secondary state ("Handled by you"). */
export function QuietPill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5 text-xs leading-4 font-medium text-secondary">
      {children}
    </span>
  );
}

/**
 * The time of the last message as an inbox shows it: the clock time today, "yesterday",
 * the weekday within a week, then a short date. The full date is the tooltip.
 */
export function ListTime({ value, timeZone }: { value: string | null; timeZone: string }) {
  const { i18n } = useTranslation();
  if (!value) return null;
  const date = new Date(value);
  const lang = i18n.language;
  const days = daysAgo(value, timeZone);
  let label: string;
  if (days <= 0) label = date.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit", timeZone });
  else if (days === 1) label = new Intl.RelativeTimeFormat(lang, { numeric: "auto" }).format(-1, "day");
  else if (days < 7) label = date.toLocaleDateString(lang, { weekday: "short", timeZone });
  else
    label = date.toLocaleDateString(lang, {
      day: "numeric",
      month: "short",
      timeZone,
      ...(dayKey(date, timeZone).slice(0, 4) !== dayKey(new Date(), timeZone).slice(0, 4) ? { year: "numeric" } : {}),
    });
  return (
    <time
      dateTime={value}
      title={date.toLocaleString(lang, { dateStyle: "medium", timeStyle: "short", timeZone })}
      className="inline-block shrink-0 text-xs leading-5 whitespace-nowrap text-secondary tabular-nums first-letter:uppercase"
    >
      {label}
    </time>
  );
}

/**
 * The Instagram account choice of a list. Hidden when there is nothing to choose; the label
 * stays available to assistive technology while the visible control stays compact.
 */
export function AccountSelect({
  accounts,
  value,
  onChange,
  allLabel,
}: {
  accounts: SocialAccount[];
  value: string;
  onChange: (value: string) => void;
  /** When given, an "all accounts" option with an empty value comes first. */
  allLabel?: string;
}) {
  const { t } = useTranslation();
  return (
    <label className="relative block min-w-0">
      <span className="sr-only">{t("agent.account")}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={`min-h-10 w-full min-w-0 cursor-pointer appearance-none truncate rounded-xl border border-border bg-surface-subtle py-2 pr-9 pl-3 font-medium text-primary transition-colors hover:border-control ${FOCUS}`}
      >
        {allLabel !== undefined ? <option value="">{allLabel}</option> : null}
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>
            @{a.username ?? t("agent.account")}
          </option>
        ))}
      </select>
      <ChevronDownIcon aria-hidden="true" className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-base text-secondary" />
    </label>
  );
}

/** A compact empty or low-data state for a pane: an icon tile, one line and an optional hint or action. */
export function PaneEmpty({
  icon,
  title,
  hint,
  action,
  testId,
}: {
  icon: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
  testId?: string;
}) {
  return (
    <div data-testid={testId} className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <span aria-hidden="true" className="mb-1 flex size-10 items-center justify-center rounded-xl bg-surface-subtle text-lg text-action">
        {icon}
      </span>
      <p className="font-heading text-base font-semibold text-primary">{title}</p>
      {hint ? <p className="max-w-xs text-metadata text-secondary">{hint}</p> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

/** One-line toned notice inside a pane (public-surface note, information-only note). */
export function PaneNote({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "attention" }) {
  return (
    <div
      role="note"
      className={`flex items-start gap-2.5 rounded-xl px-3 py-2.5 text-metadata ${
        tone === "attention" ? "bg-attention-subtle text-primary" : "bg-surface-subtle text-secondary"
      }`}
    >
      <InfoIcon aria-hidden="true" className={`mt-0.5 shrink-0 text-base ${tone === "attention" ? "text-attention" : "text-action"}`} />
      <p className="min-w-0">{children}</p>
    </div>
  );
}
