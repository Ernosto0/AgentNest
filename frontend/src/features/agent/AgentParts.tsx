import { useId, type HTMLAttributes, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { FOCUS } from "@/features/home/DashboardPanel";
import { MODE_TONE, TONE_PILL, stateIcon, stateLabel, stateTone, type Mode } from "./presentation";

export { FOCUS };

/** A server state as an icon + word pill. The word carries the meaning; tone only reinforces it. */
export function StatePill({ state, className = "" }: { state: string; className?: string }) {
  const { t } = useTranslation();
  const { icon: Icon, spins } = stateIcon(state);
  return (
    <span
      data-status={state}
      className={`inline-flex max-w-full items-center gap-1 rounded-full px-2 py-px text-xs leading-5 font-semibold ${TONE_PILL[stateTone(state)]} ${className}`}
    >
      <Icon aria-hidden="true" className={`shrink-0 text-[0.8125rem] ${spins ? "motion-safe:animate-spin" : ""}`} />
      <span className="min-w-0 [overflow-wrap:anywhere]">{stateLabel(state, t)}</span>
    </span>
  );
}

/** Square tile in the state's tone for the leading edge of a feed row. */
export function StateTile({ state, icon }: { state: string; icon?: ReactNode }) {
  const { icon: Icon, spins } = stateIcon(state);
  return (
    <span
      aria-hidden="true"
      className={`flex size-8 shrink-0 items-center justify-center rounded-lg text-base ${TONE_PILL[stateTone(state)]}`}
    >
      {icon ?? <Icon className={spins ? "motion-safe:animate-spin" : ""} />}
    </span>
  );
}

/** The delegation mode in words: "Off", "Asks first", "Automatic", or "Varies" for mixed actions. */
export function ModeChip({ mode, className = "" }: { mode: Mode | "mixed"; className?: string }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-px text-[11px] leading-5 font-semibold ${TONE_PILL[MODE_TONE[mode]]} ${className}`}>
      {t(`agent.modeShort.${mode}`)}
    </span>
  );
}

/** A plain white working surface (Card's padding is unlayered, so the redesign uses its own). */
export function Surface({
  as: Tag = "section",
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "aside" }) {
  return (
    <Tag {...props} className={`flex min-w-0 flex-col rounded-2xl border border-border bg-surface ${className}`}>
      {children}
    </Tag>
  );
}

/** Section title row used by every assistant surface. */
export function SectionTitle({
  id,
  icon,
  title,
  meta,
  action,
}: {
  id: string;
  icon?: ReactNode;
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-1">
      <div className="flex min-w-0 flex-1 basis-48 items-center gap-3">
        {icon ? (
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-subtle text-base text-action">
            {icon}
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 id={id} className="font-heading text-base leading-snug font-semibold tracking-tight text-primary">
            {title}
          </h2>
          {meta ? <div className="text-xs leading-5 text-secondary">{meta}</div> : null}
        </div>
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </div>
  );
}

/**
 * A row of mutually exclusive choices rendered as one segmented control (native radios, so arrow
 * keys, labels and form semantics come for free).
 */
export function Segmented<V extends string>({
  label,
  hideLabel = false,
  value,
  options,
  onChange,
  disabled = false,
  name,
  stretch = false,
  className = "",
}: {
  label: string;
  hideLabel?: boolean;
  value: V;
  /** `lang` marks a label written in another language (e.g. "English" on a Turkish screen). */
  options: { value: V; label: string; lang?: string }[];
  onChange: (value: V) => void;
  disabled?: boolean;
  name?: string;
  stretch?: boolean;
  className?: string;
}) {
  const autoName = useId();
  return (
    <fieldset className={`min-w-0 ${className}`} disabled={disabled}>
      <legend className={hideLabel ? "sr-only" : "mb-1.5 text-metadata font-semibold text-primary"}>{label}</legend>
      <div className={`flex min-w-0 flex-wrap gap-1 rounded-xl bg-surface-subtle p-1 ring-1 ring-border/70 ring-inset ${stretch ? "w-full" : "w-fit max-w-full"}`}>
        {options.map((option) => (
          <label
            key={option.value}
            lang={option.lang}
            className={`relative inline-flex min-h-9 cursor-pointer items-center justify-center rounded-lg px-3 text-metadata font-semibold whitespace-nowrap text-secondary transition-colors select-none pointer-coarse:min-h-11 has-checked:bg-surface has-checked:text-primary has-checked:shadow-[0_1px_2px_rgb(37_59_49/0.10)] has-checked:ring-1 has-checked:ring-border has-focus-visible:outline-2 has-focus-visible:outline-offset-1 has-focus-visible:outline-focus has-disabled:cursor-not-allowed has-disabled:opacity-70 [&:not(:has(:checked)):not(:has(:disabled))]:hover:bg-surface/70 [&:not(:has(:checked)):not(:has(:disabled))]:hover:text-primary ${stretch ? "flex-1" : ""}`}
          >
            <input
              type="radio"
              className="sr-only"
              name={name ?? autoName}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Day header for grouped feeds: "Today", "Yesterday" or a medium date on the workspace clock. */
export function DayLabel({ day, today, yesterday }: { day: string; today: string; yesterday: string }) {
  const { t, i18n } = useTranslation();
  const text =
    day === today
      ? t("content.when.today")
      : day === yesterday
        ? t("content.when.yesterday")
        : new Date(`${day}T12:00:00Z`).toLocaleDateString(i18n.language, { dateStyle: "medium", timeZone: "UTC" });
  return <h3 className="text-xs font-semibold tracking-wide text-secondary uppercase">{text}</h3>;
}
