import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { MetricItem } from "@/api/types";
import { ChevronRightIcon, ClockIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { formatValue } from "./format";

/** One record behind a report number: a customer by handle, when, and its measure if it has one. */
export function ItemRow({ item, when }: { item: MetricItem; when: string | null }) {
  const { t, i18n } = useTranslation();
  const route = item.link?.route;

  return (
    <div
      className="group flex items-center justify-between gap-4 p-4 transition-colors hover:bg-surface-subtle/60"
      data-testid="metric-item"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          {route ? (
            <Link
              to={route}
              className="font-heading font-semibold text-primary underline underline-offset-2 hover:text-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              {item.label}
            </Link>
          ) : (
            <span className="font-heading font-semibold text-primary">{item.label}</span>
          )}
          {item.is_simulated ? <SimulatedBadge /> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-secondary">
          {when ? (
            <span className="inline-flex items-center gap-1 rounded-control bg-surface-subtle border border-border px-2 py-0.5 font-medium">
              <ClockIcon className="text-xs" />
              {when}
            </span>
          ) : null}
          {typeof item.measure === "number" ? (
            <span className="rounded-control bg-assistant border border-border px-2 py-0.5 font-semibold text-primary">
              {t("reports.minutes", { value: formatValue(item.measure, i18n.language) })}
            </span>
          ) : null}
        </div>
      </div>
      {route ? (
        <div className="flex shrink-0 items-center pl-2 text-secondary group-hover:translate-x-0.5 group-hover:text-primary transition-transform">
          <ChevronRightIcon className="text-xl" />
        </div>
      ) : null}
    </div>
  );
}
