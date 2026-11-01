import { useTranslation } from "react-i18next";
import type { Approval } from "@/api/types";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { actionLabelKey } from "@/features/agent/hooks";
import { useExactAction } from "@/features/agent-work/hooks";

export function AgentApprovalBody({ approval }: { approval: Approval }) {
  const { workspace } = useCurrentWorkspace();
  const { t } = useTranslation();
  const action = useExactAction(workspace.id, approval.subject.id);
  if (action.isPending) return <p className="text-sm text-secondary">{t("common.loading")}</p>;
  if (action.isError) return <ErrorMessage error={action.error} />;
  const a = action.data;
  return (
    <section className="flex flex-col gap-2 rounded-control border border-border bg-surface-subtle p-3.5 shadow-xs" aria-label={t("agentWork.exactAction")}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-heading font-semibold text-primary">{t(actionLabelKey(a.action_type))}</h2>
        {a.is_simulated ? <SimulatedBadge /> : null}
      </div>
      <p className="text-xs text-muted">
        {t("agentWork.version")}: {a.version}
      </p>
      {a.target_text ? (
        <blockquote className="my-2 border-l-2 border-border pl-3 text-sm text-secondary italic whitespace-pre-wrap break-words">
          {a.target_text}
        </blockquote>
      ) : null}
      {a.text ? <p className="whitespace-pre-wrap break-words text-sm text-primary">{a.text}</p> : null}
      {a.content ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm break-words">
          {Object.entries(a.content)
            .filter(
              ([k, v]) =>
                ["caption", "content_type", "scheduled_at", "execute_before"].includes(k) &&
                v !== null,
            )
            .map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-secondary font-medium">
                  {t(
                    k === "caption"
                      ? "agentWork.caption"
                      : k === "content_type"
                        ? "content.typeLabel"
                        : k === "scheduled_at"
                          ? "content.schedule.title"
                          : "agentWork.expires",
                  )}
                </dt>
                <dd className="text-primary">{String(v)}</dd>
              </div>
            ))}
        </dl>
      ) : null}
      {a.version !== approval.subject.version ||
      a.payload_hash !== approval.payload_hash ||
      a.status !== "waiting_approval" ? (
        <p role="status" className="rounded-control border border-attention bg-attention-subtle p-2.5 text-xs text-attention font-medium">
          {t("agentWork.stalePreview")}
        </p>
      ) : null}
    </section>
  );
}
