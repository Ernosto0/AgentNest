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
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      {icon ? <div className="text-3xl text-slate-400">{icon}</div> : null}
      <Title className="text-base font-medium text-slate-900">{title}</Title>
      {description ? <p className="max-w-prose text-sm text-slate-600">{description}</p> : null}
      {action}
    </div>
  );
}
