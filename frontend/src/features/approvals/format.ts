/** Plain helpers for approvals (kept out of component files). */

export interface ImpactItem {
  referrer_type: string;
  total: number;
}

/** `summary.impact` as the API stores it (`{total, items}`); anything else is ignored. */
export function readImpact(summary: Record<string, unknown>): { total: number; items: ImpactItem[] } {
  const raw = summary.impact;
  if (typeof raw !== "object" || raw === null) return { total: 0, items: [] };
  const impact = raw as { total?: unknown; items?: unknown };
  const items = Array.isArray(impact.items)
    ? impact.items.flatMap((item) =>
        typeof item === "object" && item !== null && "referrer_type" in item
          ? [{ referrer_type: String(item.referrer_type), total: Number((item as { total?: unknown }).total ?? 0) }]
          : [],
      )
    : [];
  return { total: Number(impact.total ?? 0), items };
}

/** `command.update_fact` -> the catalog key suffix `command_update_fact`. */
export const actionKey = (action: string) => action.replace(/\./g, "_");
