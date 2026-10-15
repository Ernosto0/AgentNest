import type { FactCategory, TemplateItem } from "@/api/types";

/** Order of the category list (user-journeys.md J1: contact, location, hours, services, prices…). */
export const CATEGORY_ORDER: FactCategory[] = [
  "identity",
  "contact",
  "location",
  "hours",
  "service",
  "pricing",
  "promotion",
  "booking",
  "policy",
  "schedule",
  "faq",
  "brand",
  "escalation",
  "custom",
];

export function isCategory(value: string | undefined): value is FactCategory {
  return value !== undefined && (CATEGORY_ORDER as string[]).includes(value);
}

/** The tr/en label in the UI language, falling back to whichever exists. */
export function pickLabel(label: Record<string, string>, language: string): string {
  const preferred = language.startsWith("en") ? "en" : "tr";
  return label[preferred] ?? label.tr ?? label.en ?? Object.values(label)[0] ?? "";
}

export function uiLocale(language: string): "tr" | "en" {
  return language.startsWith("en") ? "en" : "tr";
}

/** `key` of a new pattern/custom fact from the label the owner typed (ASCII, snake_case). */
export function slugFromLabel(label: string): string {
  return label
    .normalize("NFC")
    .replace(/İ/g, "i")
    .replace(/I/g, "i")
    .toLowerCase()
    .replace(/[çğıöşü]/g, (c) => ({ ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u" })[c] ?? c)
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60);
}

export function keyPrefix(item: TemplateItem | null, category: FactCategory): string {
  if (item?.pattern) return item.pattern.replace(/\.\*$/, "");
  return category;
}
