import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";
import type { MetricItem } from "@/api/types";
import { NotFoundPage } from "@/app/NotFoundPage";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { dayLabel, isLocalDay } from "./dates";
import { formatValue } from "./format";
import { useDailyReport, useMetricItems } from "./hooks";

/** The records behind one number of the report. Their count is the number (AC-E3). */
export function MetricItems() {
  const params = useParams();
  if (!isLocalDay(params.date) || !params.key) return <NotFoundPage />;
  return <MetricItemsScreen date={params.date} metricKey={params.key} />;
}

function MetricItemsScreen({ date, metricKey }: { date: string; metricKey: string }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [params] = useSearchParams();
  const snapshot = params.get("snapshot_id");
  const items = useMetricItems(workspace.id, date, metricKey, snapshot);
  // The report carries the shortcut to an existing screen, where there is an exact one.
  const pinned = items.data?.pages[0]?.snapshot_id ?? snapshot;
  const report = useDailyReport(workspace.id, date, pinned);
  const screen = report.data?.metrics.find((metric) => metric.key === metricKey)?.screen_link?.route;
  const rows = items.data?.pages.flatMap((page) => page.items) ?? [];
  const value = items.data?.pages[0]?.value ?? null;
  const label = t(`reports.metrics.${metricKey}`, { defaultValue: metricKey });
  const isMedian = metricKey === "median_first_response_minutes";

  const when = (iso: string) =>
    new Date(iso).toLocaleString(i18n.language, {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: workspace.timezone,
    });

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <Link
        to={`/w/${workspace.id}/more/reports?date=${date}${pinned ? `&snapshot_id=${pinned}` : ""}`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-focus"
      >
        <span aria-hidden="true">← </span>{t("reports.backToReport")}
      </Link>
      <div>
        <h1 className="text-2xl font-heading font-semibold text-primary">{label}</h1>
        <p className="mt-1 text-sm text-secondary">{dayLabel(date, i18n.language)}</p>
        {value !== null ? (
          <p className="mt-2 text-lg font-medium text-primary" data-testid="metric-count">
            {isMedian
              ? t("reports.medianOf", { value: formatValue(value, i18n.language) })
              : t("reports.total", { total: formatValue(value, i18n.language) })}
          </p>
        ) : null}
        {screen ? (
          <Link to={screen} className="mt-1 inline-block text-sm font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-focus">
            {t("reports.openScreen")}
          </Link>
        ) : null}
      </div>

      {items.isError ? <ErrorMessage error={items.error} /> : null}
      {items.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
      {items.data && rows.length === 0 ? <EmptyState title={t("reports.noItems")} /> : null}
      {rows.length > 0 ? (
        <Card className="p-0 overflow-hidden">
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

function ItemRow({ item, when }: { item: MetricItem; when: string | null }) {
  const { t, i18n } = useTranslation();
  const route = item.link?.route;
  return (
    <div className="flex flex-col gap-1 p-4" data-testid="metric-item">
      <div className="flex flex-wrap items-center gap-2">
        {route ? (
          <Link to={route} className="font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-focus">
            {item.label}
          </Link>
        ) : (
          <span className="font-medium text-primary">{item.label}</span>
        )}
        {item.is_simulated ? <SimulatedBadge /> : null}
      </div>
      <p className="text-xs text-secondary">
        {[
          when,
          typeof item.measure === "number"
            ? t("reports.minutes", { value: formatValue(item.measure, i18n.language) })
            : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </div>
  );
}
