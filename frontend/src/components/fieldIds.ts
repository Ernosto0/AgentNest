import { useId } from "react";

export const FIELD_CONTROL = "w-full min-w-0 rounded-control border border-control bg-surface px-3 text-form text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:bg-surface-subtle read-only:bg-surface-subtle aria-invalid:border-danger";

/** Preserve supplied IDs and descriptions while linking all owned feedback. */
export function useFieldIds(id?: string, describedBy?: string, hint?: string, error?: string) {
  const generated = useId();
  const controlId = id ?? generated;
  const hintId = `${controlId}-hint`;
  const errorId = `${controlId}-error`;
  return { id: controlId, hintId, errorId, describedBy: [describedBy, hint ? hintId : undefined, error ? errorId : undefined].filter(Boolean).join(" ") || undefined };
}
