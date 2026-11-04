import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
  /** Use "h1" when the empty state is the whole page; otherwise it is plain text. */
  titleAs?: "p" | "h1" | "h2";
}

/** Empty states explain and teach (user-journeys.md §3 rule 6); they are never blank. */
export function EmptyState({ title, description, icon, action, titleAs: Title = "p" }: EmptyStateProps) {
  return (
    <div className="flex min-w-0 flex-col items-center justify-center gap-3.5 rounded-2xl border border-dashed border-border/80 bg-surface/70 px-6 py-12 text-center shadow-2xs">
      {icon ? (
        <div aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-subtle text-action border border-border/70 shadow-2xs">
          {icon}
        </div>
      ) : null}
      <Title className="text-section font-bold tracking-tight text-primary">{title}</Title>
      {description ? <p className="max-w-md text-body text-secondary leading-relaxed">{description}</p> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}
