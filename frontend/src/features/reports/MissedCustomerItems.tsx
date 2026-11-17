import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { NotFoundPage } from "@/app/NotFoundPage";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { PageHeader } from "@/components/Layout";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { isLocalDay } from "./dates";
import { formatValue } from "./format";
import { ItemRow } from "./ItemRow";
import { useMissedItems } from "./missedHooks";
import { weekLabel } from "./weeks";

const KEYS = new Set([
  "after_hours_dms",
  "first_reply_median_minutes",
  "unanswered_conversations",
  "answered_questions",
  "after_hours_price_answers",
]);

/** The records behind one number of the weekly report. Their count is the number. */
export function MissedCustomerItems() {
  const params = useParams();
  if (!isLocalDay(params.week) || !params.key || !KEYS.has(params.key)) return <NotFoundPage embedded />;
  return <Screen week={params.week} metricKey={params.key} />;
}

function Screen({ week, metricKey }: { week: string; metricKey: string }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const items = useMissedItems(workspace.id, week, metricKey);
  const rows = items.data?.pages.flatMap((page) => page.items) ?? [];
  const value = items.data?.pages[0]?.value ?? null;
  const label = t(`reports.missed.metrics.${metricKey}`);
  const isMedian = metricKey === "first_reply_median_minutes";
  const when = (iso: string) =>
    new Date(iso).toLocaleString(i18n.language, { dateStyle: "short", timeStyle: "short", timeZone: workspace.timezone });

  return (
    <div className="flex flex-col gap-6 w-full">
      <div>
        <Link
          to={`/w/${workspace.id}/more/reports/missed-customers?week=${week}`}
          className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <span aria-hidden="true">← </span>
          {t("reports.missed.backToReport")}
        </Link>
      </div>
      <PageHeader title={label} description={weekLabel(week, i18n.language)} />
      {value !== null ? (
        <p className="border-b border-border pb-3 text-section font-semibold tabular-nums text-primary" data-testid="metric-count">
          {isMedian
            ? t("reports.medianOf", { value: formatValue(value, i18n.language) })
            : t("reports.total", { total: formatValue(value, i18n.language) })}
        </p>
      ) : null}

      {items.isError ? <ErrorMessage error={items.error} /> : null}
      {items.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
      {items.data && rows.length === 0 ? <EmptyState title={t("reports.noItems")} /> : null}
      {rows.length > 0 ? (
        <Card className="p-0 overflow-hidden shadow-xs">
          <ul className="divide-y divide-border" aria-label={label}>
            {rows.map((item) => (
              <li key={`${item.kind}-${item.id}`}>
                <ItemRow item={item} when={item.occurred_at ? when(item.occurred_at) : null} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      {items.hasNextPage ? (
        <div>
          <Button variant="secondary" disabled={items.isFetchingNextPage} onClick={() => items.fetchNextPage()}>
            {items.isFetchingNextPage ? t("common.loading") : t("reports.loadMore")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
