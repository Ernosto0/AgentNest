import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { Field, type FieldFeedback } from "./Field";
import { FIELD_CONTROL, useFieldIds } from "./fieldIds";

export function TextAreaField({ label, hint, error, id, "aria-describedby": describedBy, "aria-invalid": invalid, className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & FieldFeedback) {
  const ids = useFieldIds(id, describedBy, hint, error);
  return <Field label={label} hint={hint} error={error} {...ids}><textarea rows={3} {...props} id={ids.id} aria-invalid={error ? true : invalid} aria-describedby={ids.describedBy} className={`${FIELD_CONTROL} py-2 ${className}`} /></Field>;
}

export function SelectField({ label, hint, error, id, "aria-describedby": describedBy, "aria-invalid": invalid, className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement> & FieldFeedback) {
  const ids = useFieldIds(id, describedBy, hint, error);
  return <Field label={label} hint={hint} error={error} {...ids}><select {...props} id={ids.id} aria-invalid={error ? true : invalid} aria-describedby={ids.describedBy} className={`${FIELD_CONTROL} min-h-11 ${className}`} /></Field>;
}

/** Native checkbox/radio semantics; labels and feedback remain clickable/readable. */
export function ChoiceField({ label, hint, error, id, "aria-describedby": describedBy, "aria-invalid": invalid, type = "checkbox", className = "", ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & FieldFeedback & { type?: "checkbox" | "radio" }) {
  const ids = useFieldIds(id, describedBy, hint, error);
  return <div className="min-w-0">
    <label htmlFor={ids.id} className="flex min-h-11 cursor-pointer items-center gap-3 text-form text-primary">
      <input {...props} type={type} id={ids.id} aria-invalid={error ? true : invalid} aria-describedby={ids.describedBy} className={`size-5 shrink-0 accent-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${className}`} />
      <span>{label}</span>
    </label>
    {hint ? <p id={ids.hintId} className="text-metadata text-secondary">{hint}</p> : null}
    {error ? <p id={ids.errorId} className="text-body text-danger">{error}</p> : null}
  </div>;
}
