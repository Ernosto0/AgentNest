import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ErrorMessage } from "@/components/ErrorMessage";
import { BookIcon, ChevronRightIcon } from "@/components/icons";
import { SkeletonRows } from "@/features/home/DashboardPanel";
import { pickLabel } from "@/features/knowledge/labels";
import { useLearnedMonth } from "@/features/knowledge/learning";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS, SectionTitle, Surface } from "./AgentParts";

/**
 * "Learned N things from you this month": only facts the owner verified from their own answers,
 * each linking to the fact in Business knowledge. Counted on the server from the fact history.
 */
export function LearnedThisMonth() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const learned = useLearnedMonth(workspace.id);
  const base = `/w/${workspace.id}/more/knowledge`;

  return (
    <Surface aria-labelledby="agent-learned-title" data-testid="agent-learned" className="gap-3 p-4 sm:p-5">
      <SectionTitle
        id="agent-learned-title"
        icon={<BookIcon />}
        title={t("agentWork.learning.title")}
        meta={learned.data ? t("agentWork.learning.count", { count: learned.data.count }) : undefined}
      />
      {learned.isPending ? <SkeletonRows label={t("common.loading")} rows={2} /> : null}
      {learned.isError ? <ErrorMessage error={learned.error} /> : null}
      {learned.data && learned.data.count === 0 ? (
        <p className="text-body text-secondary">{t("agentWork.learning.empty")}</p>
      ) : null}
      {learned.data && learned.data.items.length > 0 ? (
        <ul className="flex min-w-0 flex-col divide-y divide-border/70">
          {learned.data.items.map((fact) => (
            <li key={fact.fact_id} className="min-w-0">
              <Link
                to={`${base}/${fact.category}#fact-${fact.key}`}
                className={`group/link flex min-h-11 min-w-0 items-center justify-between gap-3 rounded-control py-2 text-body font-medium text-primary ${FOCUS}`}
              >
                <span className="min-w-0 [overflow-wrap:anywhere] group-hover/link:underline">
                  {pickLabel(fact.label, i18n.language)}
                </span>
                <ChevronRightIcon aria-hidden="true" className="shrink-0 text-secondary" />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </Surface>
  );
}
