import type { InputHTMLAttributes, Ref } from "react";
import { Field, type FieldFeedback } from "./Field";
import { FIELD_CONTROL, useFieldIds } from "./fieldIds";

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & FieldFeedback & { ref?: Ref<HTMLInputElement> };

export function TextField({ label, hint, error, id, "aria-describedby": describedBy, "aria-invalid": invalid, className = "", ...props }: TextFieldProps) {
  const ids = useFieldIds(id, describedBy, hint, error);
  return (
    <Field label={label} hint={hint} error={error} {...ids}>
      <input
        {...props}
        id={ids.id}
        aria-invalid={error ? true : invalid}
        aria-describedby={ids.describedBy}
        className={`${FIELD_CONTROL} min-h-11 ${className}`}
      />
    </Field>
  );
}
