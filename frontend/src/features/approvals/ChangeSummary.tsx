import { useTranslation } from "react-i18next";
import { readImpact } from "./format";

function text(summary: Record<string, unknown>, key: string): string | null {
  const value = summary[key];
  return typeof value === "string" && value !== "" ? value : null;
}

/**
 * What will change, from an approval's `summary`: the label and the old and new value. It
 * renders only strings the server already formatted, so no price is ever computed here.
 */
export function ChangeSummary({
  summary,
  fromKey,
  toKey,
}: {
  summary: Record<string, unknown>;
  fromKey: "command.confirm.from" | "approvals.detail.from";
  toKey: "command.confirm.to" | "approvals.detail.to";
}) {
  const { t } = useTranslation();
  const label = text(summary, "label");
  const before = text(summary, "old_formatted");
  const after = text(summary, "new_formatted");

  return (
    <div className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-4 shadow-xs">
      {label ? <p className="text-base font-heading font-semibold text-primary break-words">{label}</p> : null}
      {before !== null || after !== null ? (
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] items-center gap-3">
          <div className="rounded-control border border-border bg-surface-subtle p-3.5 shadow-2xs">
            <span className="block text-xs font-semibold uppercase tracking-wider text-secondary">{t(fromKey)}</span>
            <div className="mt-1 min-w-0 break-words text-sm font-medium text-secondary line-through" data-testid="change-from">
              {before ?? "–"}
            </div>
          </div>
          <div className="hidden sm:flex items-center justify-center text-secondary">
            <span className="text-xl font-bold" aria-hidden="true">→</span>
          </div>
          <div className="rounded-control border border-success/30 bg-success-subtle/50 p-3.5 shadow-2xs">
            <span className="block text-xs font-semibold uppercase tracking-wider text-action">{t(toKey)}</span>
            <div className="mt-1 min-w-0 text-lg font-heading font-bold break-words text-action" data-testid="change-to">
              {after ?? "–"}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function ImpactSummary({
  summary,
  titleKey,
  noneKey,
}: {
  summary: Record<string, unknown>;
  titleKey: "command.confirm.impactTitle" | "approvals.detail.impactTitle";
  noneKey: "command.confirm.impactNone" | "approvals.detail.impactNone";
}) {
  const { t } = useTranslation();
  const impact = readImpact(summary);
  if (impact.total === 0) {
    return <p className="text-sm text-secondary">{t(noneKey)}</p>;
  }
  return (
    <div className="rounded-panel border border-border bg-surface p-4 shadow-xs">
      <p className="text-sm font-heading font-semibold text-primary">{t(titleKey)}</p>
      <ul className="mt-2.5 flex flex-col gap-1.5 text-sm text-secondary">
        {impact.items.map((item) => (
          <li key={item.referrer_type} className="flex items-center justify-between gap-2 rounded-control bg-surface-subtle border border-border px-3 py-2">
            <span>
              {t(`approvals.referrer.${item.referrer_type}`, { defaultValue: item.referrer_type })}:{" "}
              <span className="font-semibold text-primary">{t("command.confirm.impactCount", { count: item.total })}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
