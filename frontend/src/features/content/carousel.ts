import type { TFunction } from "i18next";

export const CAROUSEL_MAX = 10;
export function move(ids: readonly string[], from: number, to: number): string[] {
  if (from < 0 || to < 0 || from >= ids.length || to >= ids.length || from === to) return [...ids];
  const next = [...ids];
  const [id] = next.splice(from, 1);
  if (id !== undefined) next.splice(to, 0, id);
  return next;
}
export const remove = (ids: readonly string[], index: number) => ids.filter((_, i) => i !== index);
export const append = (ids: readonly string[], added: readonly string[], max = CAROUSEL_MAX) =>
  [...new Set([...ids, ...added])].slice(0, max);
export const sameOrder = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((id, i) => id === b[i]);

export const CAROUSEL_CODES = ["CAROUSEL_TOO_FEW_ITEMS", "CAROUSEL_TOO_MANY_ITEMS", "CAROUSEL_DUPLICATE_MEDIA", "CAROUSEL_MIXED_ASPECT_RATIO"] as const;
export function carouselMessage(code: string, params: Record<string, unknown>, t: TFunction): string | null {
  if (!(CAROUSEL_CODES as readonly string[]).includes(code)) return null;
  return t(`content.editor.checks.${code}`, { min: 2, max: 10, ...params,
    positions: Array.isArray(params.positions) ? params.positions.join(", ") : params.positions,
  });
}
