// Compatibility exports: existing editors keep their imports during migration.
export { SelectField, TextAreaField } from "@/components/FormFields";

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
