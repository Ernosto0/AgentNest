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
  if (action.isPending) return <p>{t("common.loading")}</p>;
  if (action.isError) return <ErrorMessage error={action.error} />;
  const a = action.data;
  return (
    <section className="rounded-lg bg-slate-50 p-3" aria-label={t("agentWork.exactAction")}>
      <h2 className="font-semibold">{t(actionLabelKey(a.action_type))}</h2>
      {a.is_simulated ? <SimulatedBadge /> : null}
      <p>
        {t("agentWork.version")}: {a.version}
      </p>
      {a.target_text ? (
        <blockquote className="my-2 border-l-2 pl-3 whitespace-pre-wrap break-words">
          {a.target_text}
        </blockquote>
      ) : null}
      {a.text ? <p className="whitespace-pre-wrap break-words">{a.text}</p> : null}
      {a.content ? (
        <dl className="break-words">
          {Object.entries(a.content)
            .filter(
              ([k, v]) =>
                ["caption", "content_type", "scheduled_at", "execute_before"].includes(k) &&
                v !== null,
            )
            .map(([k, v]) => (
              <div key={k}>
                <dt>
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
                <dd>{String(v)}</dd>
              </div>
            ))}
        </dl>
      ) : null}
      {a.version !== approval.subject.version ||
      a.payload_hash !== approval.payload_hash ||
      a.status !== "waiting_approval" ? (
        <p role="status">{t("agentWork.stalePreview")}</p>
      ) : null}
    </section>
  );
}
