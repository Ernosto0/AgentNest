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
    <section
      className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-4 shadow-xs"
      aria-label={t("agentWork.exactAction")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-heading font-semibold text-primary">{t(actionLabelKey(a.action_type))}</h2>
          {a.is_simulated ? <SimulatedBadge /> : null}
        </div>
        <span className="rounded-control bg-surface-subtle border border-border px-2.5 py-0.5 text-xs font-medium text-secondary">
          {t("agentWork.version")}: {a.version}
        </span>
      </div>

      {a.target_text ? (
        <blockquote className="my-1 rounded-control border-l-4 border-control bg-surface-subtle p-3.5 text-sm text-secondary italic whitespace-pre-wrap break-words">
          {a.target_text}
        </blockquote>
      ) : null}

      {a.text ? (
        <div className="rounded-control border border-border bg-surface-subtle p-3.5 text-sm text-primary whitespace-pre-wrap break-words leading-relaxed">
          {a.text}
        </div>
      ) : null}

      {a.content ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm break-words rounded-control border border-border bg-surface-subtle p-3.5">
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
                <dd className="font-medium text-primary">{String(v)}</dd>
              </div>
            ))}
        </dl>
      ) : null}

      {a.version !== approval.subject.version ||
      a.payload_hash !== approval.payload_hash ||
      a.status !== "waiting_approval" ? (
        <p
          role="status"
          className="rounded-control border border-attention bg-attention-subtle p-3 text-xs text-attention font-medium"
        >
          {t("agentWork.stalePreview")}
        </p>
      ) : null}
    </section>
  );
}
