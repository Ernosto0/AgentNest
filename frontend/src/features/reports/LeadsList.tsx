import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { NotFoundPage } from "@/app/NotFoundPage";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { PageHeader } from "@/components/Layout";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { shiftDay, todayIn } from "./dates";
import { useExportLeads, useLeads } from "./leadsHooks";

const TEXT_LINK = "inline-flex min-h-11 items-center text-sm font-semibold text-action underline underline-offset-2";

export function LeadsList() {
  const { role } = useCurrentWorkspace();
  return role === "owner" || role === "manager" ? <LeadContents /> : <NotFoundPage embedded />;
}

function LeadContents() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [days, setDays] = useState(30);
  const to = todayIn(workspace.timezone);
  const from = shiftDay(to, 1 - days);
  const list = useLeads(workspace.id, from, to);
  const exporting = useExportLeads(workspace.id);
  const total = list.data?.pages[0]?.total;
  const items = list.data?.pages.flatMap((page) => page.items) ?? [];
  const download = (className: string) => (
    <Button className={className} disabled={total === undefined || total === 0 || exporting.isPending}
      pending={exporting.isPending} onClick={() => exporting.mutate({ from, to, total: total ?? 0 })}>
      {t("reports.leads.download")}
    </Button>
  );
  return (
    <div className="flex w-full min-w-0 flex-col gap-5">
      <PageHeader title={t("reports.leads.title")} description={t("reports.leads.intro")}
        action={<div className="hidden sm:block">{download("")}</div>} />
      <Link className={TEXT_LINK} to={`/w/${workspace.id}/more/reports`}>{t("reports.leads.back")}</Link>
      <div role="group" aria-label={t("reports.leads.period")} className="flex flex-wrap gap-2">
        {[7, 30, 90].map((n) => (
          <Button key={n} variant={days === n ? "primary" : "secondary"} className="min-h-11"
            aria-pressed={days === n} disabled={exporting.isPending}
            onClick={() => { setDays(n); exporting.reset(); }}>
            {t(`reports.leads.days${n}`)}
          </Button>
        ))}
      </div>
      <div className="sm:hidden">{download("w-full")}</div>
      {list.isError ? <ErrorMessage error={list.error} /> : null}
      {exporting.isError ? <ErrorMessage error={exporting.error} /> : null}
      {exporting.isSuccess ? <p role="status" className="text-sm text-secondary">
        {t("reports.leads.exported", { count: exporting.data.count })}
        {exporting.data.truncated ? ` ${t("reports.leads.truncated")}` : ""}
      </p> : null}
      {list.isPending ? <p>{t("common.loading")}</p> : null}
      {total !== undefined ? <p className="text-sm text-secondary">{t("reports.leads.count", { count: total })}</p> : null}
      {total === 0 ? <EmptyState title={t("reports.leads.empty")} description={t("reports.leads.emptyHint")} /> : null}
      <ul className="flex min-w-0 flex-col gap-3">
        {items.map((item) => (
          <li key={item.conversation_id} className="min-w-0">
            <Card className="min-w-0 break-words p-4">
              <p className="font-semibold text-primary">{item.customer_handle || t("reports.leads.customer")}</p>
              <p className="text-sm text-secondary">{new Date(item.last_question_at).toLocaleString(i18n.language, {
                dateStyle: "short", timeStyle: "short", timeZone: workspace.timezone,
              })}</p>
              <p className="text-sm font-semibold">{t(`reports.leads.${item.intent}`)}</p>
              <p className={item.last_question ? "text-primary" : "text-secondary"}>{item.last_question || t("reports.leads.noText")}</p>
              {item.link.route ? <Link className={TEXT_LINK} to={item.link.route}>{t("reports.leads.open")}</Link> : null}
            </Card>
          </li>
        ))}
      </ul>
      {list.hasNextPage ? <Button variant="secondary" pending={list.isFetchingNextPage}
        onClick={() => void list.fetchNextPage()}>{t("reports.leads.loadMore")}</Button> : null}
      <div className="space-y-2 text-sm text-secondary">
        <p>{t("reports.leads.crmNote")}</p>
        <p>{t("reports.leads.safetyNote")}</p>
        <p>{t("reports.leads.classificationNote")}</p>
        <p>{t("reports.missed.simulatedNote")}</p>
      </div>
    </div>
  );
}
