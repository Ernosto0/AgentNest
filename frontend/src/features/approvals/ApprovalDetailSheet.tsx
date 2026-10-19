import { useTranslation } from "react-i18next";
import type { Approval } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useDecideApproval } from "@/features/commands/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ChangeSummary, ImpactSummary } from "./ChangeSummary";
import { ReplyApprovalBody } from "./ReplyApprovalBody";
import { actionKey } from "./format";

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
  ]);
  const rows = Object.entries(summary).filter(
    ([name, value]) => !known.has(name) && typeof value === "string" && value !== "",
  );
  if (rows.length === 0) return null;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
      {rows.map(([name, value]) => (
        <div key={name} className="contents">
          <dt className="text-slate-600">{name}</dt>
          <dd className="min-w-0 break-words">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * One approval, rendered generically by its action: what will change, what it touches, when it
 * expires, and the two explicit decisions. The decision carries the displayed payload hash.
 */
export function ApprovalDetailSheet({ approval, onClose }: { approval: Approval; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const decide = useDecideApproval(workspace.id);
  const pending = approval.status === "pending";

  const decideWith = (decision: "approve" | "reject") =>
    decide.mutate({ approval, decision }, { onSuccess: onClose });

  return (
    <BottomSheet
      title={t("approvals.detail.title")}
      onClose={onClose}
      footer={
        pending ? (
          approval.can_decide ? (
            <div className="flex flex-wrap gap-2">
              <Button disabled={decide.isPending} onClick={() => decideWith("approve")}>
                {decide.isPending ? t("approvals.detail.deciding") : t("approvals.detail.approve")}
              </Button>
              <Button variant="secondary" disabled={decide.isPending} onClick={() => decideWith("reject")}>
                {t("approvals.detail.reject")}
              </Button>
            </div>
          ) : (
            <p className="text-sm text-slate-700">{t("approvals.detail.cannotDecide")}</p>
          )
        ) : null
      }
    >
      <div
        className="flex flex-col gap-4"
        data-testid="approval-detail"
        data-payload-hash={approval.payload_hash}
      >
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span className="font-medium text-slate-900">{t(`approvals.action.${actionKey(approval.action)}`)}</span>
          <span>·</span>
          <span>
            {approval.kind === "confirmation"
              ? t("approvals.detail.kindConfirmation")
              : t("approvals.detail.kindAuthorization")}
          </span>
          {approval.is_simulated ? <SimulatedBadge /> : null}
        </div>
        {approval.action === "reply.send" ? <ReplyApprovalBody approval={approval} /> : null}
        <ChangeSummary summary={approval.summary} fromKey="approvals.detail.from" toKey="approvals.detail.to" />
        <ExtraFields summary={approval.summary} />
        <ImpactSummary
          summary={approval.summary}
          titleKey="approvals.detail.impactTitle"
          noneKey="approvals.detail.impactNone"
        />
        <p className="text-sm text-slate-600">
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
        {decide.error ? <ErrorMessage error={decide.error} /> : null}
      </div>
    </BottomSheet>
  );
}
