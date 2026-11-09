import type { HTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRightIcon } from "@/components/icons";

/** Shared focus ring for dashboard links and controls. */
export const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

type Tone = "surface" | "assistant";

/**
 * A Today surface. Hierarchy comes from tone and spacing, not elevation:
 * plain working surfaces are white with a hairline; the assistant uses its own sage tone.
 */
export function Panel({
  tone = "surface",
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLElement> & { tone?: Tone }) {
  const toneClass = tone === "assistant" ? "bg-assistant" : "border border-border bg-surface";
  return (
    <section {...props} className={`flex min-w-0 flex-col rounded-2xl p-4 sm:p-5 ${toneClass} ${className}`}>
      {children}
    </section>
  );
}

/** Title row: optional icon tile, heading, a line of context and one trailing action. */
export function PanelHeading({
  id,
  icon,
  title,
  meta,
  action,
  iconTone = "neutral",
  wrap = false,
}: {
  id: string;
  icon?: ReactNode;
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
  iconTone?: "neutral" | "assistant";
  /** Let a wide action group (filters, toggles) drop below the title on narrow screens. */
  wrap?: boolean;
}) {
  return (
    <div className={`flex min-w-0 justify-between gap-x-4 gap-y-2 ${wrap ? "flex-wrap items-center" : "items-start"}`}>
      <div className={`flex min-w-0 items-center gap-3 ${wrap ? "" : "flex-1"}`}>
        {icon ? (
          <span
            aria-hidden="true"
            className={`flex size-8 shrink-0 items-center justify-center rounded-lg text-base ${
              iconTone === "assistant" ? "bg-action text-on-action" : "bg-surface-subtle text-action"
            }`}
          >
            {icon}
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 id={id} className="font-heading text-base leading-snug font-semibold tracking-tight text-primary">
            {title}
          </h2>
          {meta ? <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs leading-5 text-secondary">{meta}</div> : null}
        </div>
      </div>
      {action ? <div className={`flex shrink-0 items-center ${wrap ? "" : "-mt-1"}`}>{action}</div> : null}
    </div>
  );
}

/** Quiet "see more" navigation that still offers a 44 px target. */
export function PanelLink({ to, children, className = "" }: { to: string; children: ReactNode; className?: string }) {
  return (
    <Link
      to={to}
      className={`group/link -mx-1 inline-flex min-h-11 shrink-0 items-center gap-0.5 rounded-control px-1 text-metadata font-semibold text-action transition-colors hover:text-action-hover ${FOCUS} ${className}`}
    >
      <span className="underline-offset-4 group-hover/link:underline">{children}</span>
      <ChevronRightIcon className="text-base transition-transform duration-150 group-hover/link:translate-x-0.5" />
    </Link>
  );
}

/** A loading placeholder shaped like the content it replaces, with a spoken label. */
export function SkeletonRows({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div role="status" className="flex flex-col gap-3 py-1">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} aria-hidden="true" className="flex items-center gap-3">
          <div className="size-8 shrink-0 rounded-lg bg-surface-subtle motion-safe:animate-pulse" />
          <div className="flex flex-1 flex-col gap-1.5">
            <div className="h-2.5 w-2/3 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
            <div className="h-2 w-1/3 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** One-line, toned notice for states that matter but should not dominate a panel. */
export function InlineNotice({
  tone,
  icon,
  title,
  children,
  action,
  testId,
}: {
  tone: "info" | "attention" | "neutral";
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  testId?: string;
}) {
  const toneClass = {
    info: "bg-info-subtle text-info",
    attention: "bg-attention-subtle text-attention",
    neutral: "bg-surface-subtle text-secondary",
  }[tone];
  return (
    <div data-testid={testId} role="status" className={`flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 rounded-xl px-4 py-3 ${toneClass}`}>
      <div className="flex min-w-0 flex-1 basis-56 items-start gap-3">
        {icon ? <span aria-hidden="true" className="mt-0.5 shrink-0 text-lg">{icon}</span> : null}
        <div className="min-w-0">
          <p className="text-body font-semibold text-primary">{title}</p>
          {children ? <p className="text-metadata text-secondary">{children}</p> : null}
        </div>
      </div>
      {action}
    </div>
  );
}
