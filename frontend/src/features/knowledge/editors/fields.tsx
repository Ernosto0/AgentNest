import { useId, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

/** A canonical fact value as sent to and returned by the API (shape depends on the type). */
export type FactValue = Record<string, unknown>;

export interface EditorProps {
  /** The current value, used only as the starting point; the editor owns its own draft. */
  value: FactValue | null;
  /** Called with a complete value, or `null` while the input is incomplete or invalid. */
  onChange: (value: FactValue | null) => void;
  currency: string;
  allowedValues: string[];
}

const CONTROL =
  "w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-indigo-600";

export function TextAreaField({
  label,
  hint,
  className = "",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-800">
        {label}
      </label>
      <textarea id={id} rows={3} className={`${CONTROL} py-2 ${className}`} {...props} />
      {hint ? <p className="text-sm text-slate-600">{hint}</p> : null}
    </div>
  );
}

export function SelectField({
  label,
  className = "",
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-800">
        {label}
      </label>
      <select id={id} className={`${CONTROL} min-h-11 ${className}`} {...props}>
        {children}
      </select>
    </div>
  );
}
