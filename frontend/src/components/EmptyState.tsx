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
    <div className="flex min-w-0 flex-col items-center gap-3 rounded-panel border border-dashed border-control bg-surface px-6 py-10 text-center">
      {icon ? <div aria-hidden="true" className="text-3xl text-secondary">{icon}</div> : null}
      <Title className="text-form font-semibold text-primary">{title}</Title>
      {description ? <p className="max-w-prose text-body text-secondary">{description}</p> : null}
      {action}
    </div>
  );
}
