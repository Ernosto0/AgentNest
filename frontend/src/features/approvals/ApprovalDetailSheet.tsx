import { useTranslation } from "react-i18next";
import type { Approval } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useExactAction } from "@/features/agent-work/hooks";
import { useDecideApproval } from "@/features/commands/hooks";
import { useContentItem } from "@/features/content/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AgentApprovalBody } from "./AgentApprovalBody";
import { CancelContentSummary } from "./CancelContentSummary";
import { ChangeSummary, ImpactSummary } from "./ChangeSummary";
import { ContentApprovalBody } from "./ContentApprovalBody";
import { ReplyApprovalBody } from "./ReplyApprovalBody";
import { actionKey, isStaleFor } from "./format";

function localTime(value: string, language: string, timezone: string): string {
  return new Date(value).toLocaleString(language, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: timezone,
  });
}

/** Strings of the summary that the generic body does not know about, shown as plain rows. */
function ExtraFields({ summary }: { summary: Record<string, unknown> }) {
  const known = new Set([
    "label",
    "old_formatted",
    "new_formatted",
    "impact",
    "key",
    "category",
    "draft_id",
    "conversation_id",
    "window_ends_at",
    "reasons",
    // Content approvals: the ids and raw fields are shown by their own bodies.
    "content_id",
    "content_type",
    "status",
    "when",
    "title",
    "scheduled_at",
  ]);
  const rows = Object.entries(summary).filter(
    ([name, value]) => !known.has(name) && typeof value === "string" && value !== "",
  );
  if (rows.length === 0) return null;
  return (
    <div className="rounded-panel border border-border bg-surface p-4 shadow-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
        {rows.map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="text-secondary font-medium">{name}</dt>
            <dd className="min-w-0 break-words text-primary font-medium">{String(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * One approval, rendered generically by its action: what will change, what it touches, when it
 * expires, and the two explicit decisions. The decision carries the displayed payload hash.
 */
export function ApprovalDetailSheet({
  approval,
  onClose,
}: {
  approval: Approval;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const decide = useDecideApproval(workspace.id);
  const pending = approval.status === "pending";
  const isAgent = approval.subject.type === "agent_action";
  const exact = useExactAction(workspace.id, approval.subject.id, isAgent);
  const isPublish = approval.action === "content.publish" && !isAgent;
  const isCancel = approval.action === "command.cancel_content";
  // A publish approval is decided on what it covers, so the item is read first.
  const content = useContentItem(workspace.id, approval.subject.id, isPublish);
  const cannotApprove =
    (isPublish && (!content.data || isStaleFor(approval, content.data))) ||
    (isAgent &&
      (!exact.data ||
        exact.data.version !== approval.subject.version ||
        exact.data.payload_hash !== approval.payload_hash ||
        exact.data.status !== "waiting_approval"));

  const decideWith = (decision: "approve" | "reject") =>
    decide.mutate({ approval, decision }, { onSuccess: onClose });

  const statusTone = pending
    ? "text-attention bg-attention-subtle border border-attention/30"
    : approval.status === "approved"
      ? "text-success bg-success-subtle border border-success/30"
      : approval.status === "rejected"
        ? "text-danger bg-danger-subtle border border-danger/30"
        : "text-secondary bg-surface-subtle border border-border";

  return (
    <BottomSheet
      title={t("approvals.detail.title")}
      onClose={onClose}
      footer={
        pending ? (
          approval.can_decide ? (
            <div className="flex flex-wrap items-center gap-3">
              <Button
                disabled={decide.isPending || cannotApprove}
                onClick={() => decideWith("approve")}
              >
                {decide.isPending ? t("approvals.detail.deciding") : t("approvals.detail.approve")}
              </Button>
              <Button
                variant="secondary"
                disabled={decide.isPending}
                onClick={() => decideWith("reject")}
              >
                {t("approvals.detail.reject")}
              </Button>
            </div>
          ) : (
            <div className="rounded-control border border-border bg-surface-subtle p-3 w-full">
              <p className="text-sm font-medium text-secondary">{t("approvals.detail.cannotDecide")}</p>
            </div>
          )
        ) : null
      }
    >
      <div
        className="flex flex-col gap-4"
        data-testid="approval-detail"
        data-payload-hash={approval.payload_hash}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-border bg-surface-subtle p-3.5">
          <div className="flex flex-wrap items-center gap-2 text-sm text-secondary">
            <span className="font-heading font-semibold text-primary">
              {t(`approvals.action.${actionKey(approval.action)}`)}
            </span>
            <span>·</span>
            <span>
              {approval.kind === "confirmation"
                ? t("approvals.detail.kindConfirmation")
                : t("approvals.detail.kindAuthorization")}
            </span>
            {approval.is_simulated ? <SimulatedBadge /> : null}
          </div>
          <span className={`inline-flex items-center rounded-control px-2.5 py-0.5 text-xs font-medium ${statusTone}`}>
            {t(`approvals.status.${approval.status}`)}
          </span>
        </div>

        {isAgent ? <AgentApprovalBody approval={approval} /> : null}
        {approval.action === "reply.send" && !isAgent ? (
          <ReplyApprovalBody approval={approval} />
        ) : null}
        {isPublish ? (
          <ContentApprovalBody
            approval={approval}
            item={content.data}
            loading={content.isPending}
            failed={content.isError}
          />
        ) : null}
        {isCancel ? <CancelContentSummary summary={approval.summary} /> : null}
        {isPublish || isAgent ? null : (
          <>
            {isCancel ? null : (
              <ChangeSummary
                summary={approval.summary}
                fromKey="approvals.detail.from"
                toKey="approvals.detail.to"
              />
            )}
            <ExtraFields summary={approval.summary} />
            <ImpactSummary
              summary={approval.summary}
              titleKey="approvals.detail.impactTitle"
              noneKey="approvals.detail.impactNone"
            />
          </>
        )}

        <div className="flex items-center gap-2 rounded-control bg-surface-subtle border border-border px-3 py-2 text-sm text-secondary">
          <ClockIcon className="text-base shrink-0 text-secondary" />
          <p>
            {pending
              ? t("approvals.detail.expires", {
                  time: localTime(approval.expires_at, i18n.language, workspace.timezone),
                })
              : `${t(`approvals.status.${approval.status}`)}${
                  approval.decided_at
                    ? ` · ${t("approvals.detail.decidedAt", {
                        time: localTime(approval.decided_at, i18n.language, workspace.timezone),
                      })}`
                    : ""
                }`}
          </p>
        </div>

        {decide.error ? <ErrorMessage error={decide.error} /> : null}
      </div>
    </BottomSheet>
  );
}
