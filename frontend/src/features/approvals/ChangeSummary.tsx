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
    <div className="flex flex-col gap-2 rounded-control border border-border bg-surface-subtle p-3.5">
      {label ? <p className="text-base font-heading font-semibold text-primary break-words">{label}</p> : null}
      {before !== null || after !== null ? (
        <dl className="grid grid-cols-[auto_1fr] items-baseline gap-x-3 gap-y-1">
          <dt className="text-sm font-medium text-secondary">{t(fromKey)}</dt>
          <dd className="min-w-0 break-words text-muted line-through" data-testid="change-from">
            {before ?? "–"}
          </dd>
          <dt className="text-sm font-medium text-secondary">{t(toKey)}</dt>
          <dd className="min-w-0 text-lg font-heading font-bold break-words text-action" data-testid="change-to">
            {after ?? "–"}
          </dd>
        </dl>
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
    <div className="rounded-control border border-border bg-surface p-3">
      <p className="text-sm font-heading font-semibold text-primary">{t(titleKey)}</p>
      <ul className="mt-1.5 list-disc pl-5 text-sm text-secondary">
        {impact.items.map((item) => (
          <li key={item.referrer_type}>
            {t(`approvals.referrer.${item.referrer_type}`, { defaultValue: item.referrer_type })}:{" "}
            <span className="font-medium text-primary">{t("command.confirm.impactCount", { count: item.total })}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
