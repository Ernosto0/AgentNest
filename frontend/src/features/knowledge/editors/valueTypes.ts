export const VALUE_TYPES = [
  "money",
  "weekly_hours",
  "text",
  "localized_text",
  "phone",
  "email",
  "address",
  "url",
  "boolean",
  "enum",
  "string_list",
] as const;

export type ValueType = (typeof VALUE_TYPES)[number];
