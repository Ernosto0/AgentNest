import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { PolicyItem } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { AgentPage } from "@/features/agent/AgentPage";
import { useAgentOverview } from "@/features/agent/hooks";
import {
  useAutomation,
  useConnectMock,
  useReviewAutomation,
  useSaveAutomation,
  useSocialAccounts,
} from "@/features/inbox/hooks";
import { capabilityLabel } from "@/features/content/messages";
import { useCurrentWorkspace } from "@/features/workspaces/context";

type Mode = PolicyItem["mode"];
const MODES: Mode[] = ["approval", "auto", "off"];

/** The Instagram connection and how much the assistant may do alone, per kind of reply. */
export function AutomationSettings() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const accounts = useSocialAccounts(workspace.id);
  const account = accounts.data?.find((a) => a.status !== "disconnected");
  const agent = useAgentOverview(workspace.id, account?.id ?? "");

  if (accounts.isPending || (account && agent.isPending)) {
    return (
      <p role="status" className="text-sm text-secondary">
        {t("common.loading")}
      </p>
    );
  }
  if (accounts.error) return <ErrorMessage error={accounts.error} />;
  if (account && agent.error) return <ErrorMessage error={agent.error} />;
  return agent.data?.controller_mode === "agent" ? <AgentPage /> : <LegacyAutomationSettings />;
}

function LegacyAutomationSettings() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const owner = role === "owner";
  const accounts = useSocialAccounts(workspace.id);
  const connect = useConnectMock(workspace.id);
  const automation = useAutomation(workspace.id);
  const save = useSaveAutomation(workspace.id);
  const review = useReviewAutomation(workspace.id);
  // Only what the owner changed on this screen; everything else shows the saved value.
  const [edits, setEdits] = useState<Record<string, Mode>>({});

  const account = accounts.data?.find((a) => a.status !== "disconnected") ?? null;

  return (
    <div className="flex min-w-0 flex-col gap-6 max-w-4xl">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-heading font-semibold text-primary">{t("automation.title")}</h1>
        <Link className="text-sm font-medium text-action hover:text-action-hover underline" to={`/w/${workspace.id}/more/agent`}>
          {t("agent.title")}
        </Link>
      </div>

      <Card className="flex flex-col gap-4">
        <div className="border-b border-border pb-3">
          <h2 className="text-lg font-heading font-semibold text-primary">{t("automation.connection")}</h2>
        </div>
        {account ? (
          <>
            <p data-testid="account-status" className="text-base text-primary">
              <span className="font-semibold">@{account.username ?? account.id}</span> ·{" "}
              <span className="text-secondary">{t(`automation.accountStatus.${account.status}`)}</span>{" "}
              {account.is_simulated ? <SimulatedBadge /> : null}
            </p>
            <p className="text-sm text-secondary" data-testid="account-capabilities">
              {t("content.capability.title")}:{" "}
              <span className="font-medium text-primary">
                {Object.entries(account.capabilities)
                  .filter(([, granted]) => granted === true)
                  .map(([name]) => capabilityLabel(name, t))
                  .join(", ") || "–"}
              </span>
            </p>
            <Link
              to={`/w/${workspace.id}/more/settings/connections`}
              className="text-sm font-medium text-action hover:text-action-hover underline"
            >
              {t("automation.manageConnection")}
            </Link>
          </>
        ) : (
          <>
            <p className="text-sm text-secondary">{t("automation.notConnected")}</p>
            {owner ? (
              <div>
                <Button disabled={connect.isPending} onClick={() => connect.mutate()}>
                  {t("automation.connectMock")}
                </Button>
              </div>
            ) : (
              <p className="text-sm font-medium text-secondary">{t("automation.ownerOnly")}</p>
            )}
            {connect.error ? <ErrorMessage error={connect.error} /> : null}
          </>
        )}
      </Card>

      <Card className="flex flex-col gap-4">
        <div className="border-b border-border pb-3">
          <h2 className="text-lg font-heading font-semibold text-primary">{t("automation.policies")}</h2>
        </div>
        <p className="text-sm text-secondary">{t("automation.intro")}</p>
        {automation.isError ? <ErrorMessage error={automation.error} /> : null}
        {automation.data ? (
          <ul className="flex flex-col gap-3">
            {automation.data.items.map((item) => (
              <li
                key={item.action_class}
                className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-border bg-surface-subtle p-3"
              >
                <label htmlFor={`mode-${item.action_class}`} className="text-sm font-medium text-primary">
                  {t(`automation.class.${item.action_class.replace(".", "_")}`)}
                </label>
                <select
                  id={`mode-${item.action_class}`}
                  value={edits[item.action_class] ?? item.mode}
                  disabled={!owner}
                  onChange={(event) =>
                    setEdits((current) => ({ ...current, [item.action_class]: event.target.value as Mode }))
                  }
                  className="min-h-11 rounded-control border border-border bg-surface px-3 py-2 text-base text-primary shadow-xs focus-visible:outline-2 focus-visible:outline-focus disabled:opacity-60"
                >
                  {MODES.map((mode) => (
                    <option key={mode} value={mode} disabled={mode === "auto" && !automation.data?.auto_allowed}>
                      {t(`automation.mode.${mode}`)}
                    </option>
                  ))}
                </select>
              </li>
            ))}
          </ul>
        ) : null}
        {automation.data && !automation.data.auto_allowed ? (
          <p className="text-sm font-medium text-attention">{t("automation.autoNeedsReady")}</p>
        ) : null}
        {automation.data?.reviewed_at ? (
          <p className="text-sm font-medium text-secondary">{t("automation.reviewed")}</p>
        ) : null}
        {owner ? (
          <div>
            <Button
              disabled={save.isPending || !automation.data}
              onClick={() =>
                save.mutate(
                  (automation.data?.items ?? []).map((item) => ({
                    action_class: item.action_class,
                    mode: edits[item.action_class] ?? item.mode,
                  })),
                  { onSuccess: () => setEdits({}) },
                )
              }
            >
              {save.isPending ? t("common.saving") : t("automation.save")}
            </Button>
          </div>
        ) : (
          <p className="text-sm font-medium text-secondary">{t("automation.ownerOnly")}</p>
        )}
        {save.isSuccess ? (
          <p role="status" className="text-sm font-medium text-success">
            {t("automation.saved")}
          </p>
        ) : null}
        {save.error ? <ErrorMessage error={save.error} /> : null}
        {owner && automation.data && !automation.data.reviewed_at ? (
          <div className="flex flex-col gap-2 border-t border-border pt-4">
            <p className="text-sm text-secondary">{t("automation.reviewHint")}</p>
            <div>
              <Button variant="secondary" disabled={review.isPending} onClick={() => review.mutate()}>
                {t("automation.review")}
              </Button>
            </div>
            {review.error ? <ErrorMessage error={review.error} /> : null}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
