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
    <div className="flex flex-col gap-2">
      {label ? <p className="text-lg font-semibold break-words">{label}</p> : null}
      {before !== null || after !== null ? (
        <dl className="grid grid-cols-[auto_1fr] items-baseline gap-x-3 gap-y-1">
          <dt className="text-sm text-slate-600">{t(fromKey)}</dt>
          <dd className="min-w-0 break-words text-slate-700 line-through decoration-slate-400" data-testid="change-from">
            {before ?? "–"}
          </dd>
          <dt className="text-sm text-slate-600">{t(toKey)}</dt>
          <dd className="min-w-0 text-xl font-semibold break-words text-indigo-900" data-testid="change-to">
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
    return <p className="text-sm text-slate-600">{t(noneKey)}</p>;
  }
  return (
    <div>
      <p className="text-sm font-medium">{t(titleKey)}</p>
      <ul className="mt-1 list-disc pl-5 text-sm">
        {impact.items.map((item) => (
          <li key={item.referrer_type}>
            {t(`approvals.referrer.${item.referrer_type}`, { defaultValue: item.referrer_type })}:{" "}
            {t("command.confirm.impactCount", { count: item.total })}
          </li>
        ))}
      </ul>
    </div>
  );
}
