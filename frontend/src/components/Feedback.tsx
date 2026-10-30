import { useId, type ReactNode } from "react";
import { AlertIcon, CheckIcon, InfoIcon } from "./icons";

const TONES = {
  info: "border-info bg-info-subtle text-info",
  attention: "border-attention bg-attention-subtle text-attention",
  danger: "border-danger bg-danger-subtle text-danger",
  success: "border-success bg-success-subtle text-success",
};

/** Static by default. Announce only newly arrived information, not polling containers. */
export function Notice({ title, children, tone = "info", live = "off" }: { title: string; children?: ReactNode; tone?: keyof typeof TONES; live?: "off" | "polite" | "assertive" }) {
  const Icon = tone === "success" ? CheckIcon : tone === "danger" || tone === "attention" ? AlertIcon : InfoIcon;
  return <div role={live === "assertive" ? "alert" : live === "polite" ? "status" : undefined} className={`flex min-w-0 items-start gap-3 rounded-control border p-4 text-body ${TONES[tone]}`}>
    <Icon className="mt-0.5 shrink-0" /><div className="min-w-0"><p className="font-semibold">{title}</p>{children ? <div className="mt-1">{children}</div> : null}</div>
  </div>;
}

/** Render only after validation. Links move to the invalid native field. */
export function ErrorSummary({ title, errors }: { title: string; errors: { id: string; message: string }[] }) {
  const titleId = useId();
  if (!errors.length) return null;
  return <div role="alert" aria-labelledby={titleId} tabIndex={-1} className="rounded-control border border-danger bg-danger-subtle p-4 text-body text-danger focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
    <p id={titleId} className="font-semibold">{title}</p><ul className="mt-2 list-inside list-disc">{errors.map(error => <li key={error.id}><a href={`#${error.id}`} className="inline-flex min-h-11 items-center underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-focus" onClick={event => { const field = document.getElementById(error.id); if (field) { event.preventDefault(); field.focus(); field.scrollIntoView?.({ block: "center" }); } }}>{error.message}</a></li>)}</ul>
  </div>;
}

/** Local noncritical feedback; no automatic dismissal or substitute for record state. */
export function Toast({ children, dismissLabel, onDismiss }: { children: ReactNode; dismissLabel: string; onDismiss: () => void }) {
  return <div className="flex min-w-0 items-start gap-3 rounded-control border border-border bg-surface p-4 text-body text-primary shadow-float"><p role="status" className="min-w-0 flex-1">{children}</p><button type="button" onClick={onDismiss} aria-label={dismissLabel} className="min-h-11 min-w-11 rounded-control px-2 text-secondary hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"><span aria-hidden="true">×</span></button></div>;
}

/** One polite label per loading region; skeleton shapes are decorative. */
export function Skeleton({ label, rows = 3 }: { label: string; rows?: number }) {
  return <div role="status" aria-label={label} className="grid gap-3"><span className="sr-only">{label}</span>{Array.from({ length: Math.max(1, Math.min(rows, 10)) }, (_, index) => <span key={index} aria-hidden="true" className="h-5 rounded-control bg-surface-subtle motion-safe:animate-pulse" />)}</div>;
}
