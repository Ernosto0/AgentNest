import type { HTMLAttributes, ReactNode, TableHTMLAttributes } from "react";

export function PageHeader({ title, description, context, action }: { title: string; description?: string; context?: ReactNode; action?: ReactNode }) {
  return <header className="flex min-w-0 flex-wrap items-start justify-between gap-x-6 gap-y-4">
    <div className="min-w-0 flex-1 basis-64">{context}<h1 className="type-page break-words text-primary">{title}</h1>{description ? <p className="mt-2 max-w-prose text-body text-secondary">{description}</p> : null}</div>
    {action ? <div className="flex max-w-full flex-wrap items-center gap-2">{action}</div> : null}
  </header>;
}

export function PanelHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
    <div className="min-w-0"><h2 className="type-section break-words text-primary">{title}</h2>{description ? <p className="mt-1 text-body text-secondary">{description}</p> : null}</div>{action}
  </div>;
}

/** Keep navigation/filter links native; use aria-current or aria-pressed on children. */
export function FilterBar({ label, children }: { label: string; children: ReactNode }) {
  return <div role="group" aria-label={label} className="flex min-w-0 flex-wrap items-center gap-2">{children}</div>;
}

export function ListRow({ className = "", ...props }: HTMLAttributes<HTMLLIElement>) {
  return <li {...props} className={`min-w-0 border-b border-border py-4 last:border-b-0 ${className}`} />;
}

/** Horizontal scrolling belongs to this labelled region, never the whole document. */
export function DataTable({ caption, children, className = "", ...props }: TableHTMLAttributes<HTMLTableElement> & { caption: string }) {
  return <div role="region" aria-label={caption} tabIndex={0} className="max-w-full overflow-x-auto rounded-control focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
    <table {...props} className={`w-full border-collapse text-left text-body text-primary ${className}`}><caption className="sr-only">{caption}</caption>{children}</table>
  </div>;
}
