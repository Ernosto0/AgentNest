import type { ReactNode } from "react";

export interface FieldFeedback {
  label: string;
  hint?: string;
  error?: string;
}

export function Field({ label, hint, error, id, hintId, errorId, children }: FieldFeedback & { id: string; hintId: string; errorId: string; children: ReactNode }) {
  return <div className="flex min-w-0 flex-col gap-1.5">
    <label htmlFor={id} className="text-body font-medium text-primary">{label}</label>
    {children}
    {hint ? <p id={hintId} className="text-metadata text-secondary">{hint}</p> : null}
    {error ? <p id={errorId} className="text-body text-danger">{error}</p> : null}
  </div>;
}
