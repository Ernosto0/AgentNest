import { AgentPage } from "@/features/agent/AgentPage";
import { useAgentOverview } from "@/features/agent/hooks";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { PolicyItem } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
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
  const account = accounts.data?.find(a => a.status !== "disconnected");
  const agent = useAgentOverview(workspace.id, account?.id ?? "");
  if (accounts.isPending || (account && agent.isPending)) return <p role="status">{t("common.loading")}</p>;
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
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-semibold">{t("automation.title")}</h1>
      <Link className="text-indigo-700 underline" to={`/w/${workspace.id}/more/agent`}>{t("agent.title")}</Link>

      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">{t("automation.connection")}</h2>
        {account ? (
          <>
            <p data-testid="account-status">
              <span className="font-medium">@{account.username ?? account.id}</span> ·{" "}
              {t(`automation.accountStatus.${account.status}`)}{" "}
              {account.is_simulated ? <SimulatedBadge /> : null}
            </p>
            <p className="text-sm text-slate-700" data-testid="account-capabilities">
              {t("content.capability.title")}:{" "}
              {Object.entries(account.capabilities)
                .filter(([, granted]) => granted === true)
                .map(([name]) => capabilityLabel(name, t))
                .join(", ") || "–"}
            </p>
            <Link
              to={`/w/${workspace.id}/more/settings/connections`}
              className="font-semibold text-indigo-700 underline underline-offset-2"
            >
              {t("automation.manageConnection")}
            </Link>
          </>
        ) : (
          <>
            <p>{t("automation.notConnected")}</p>
            {owner ? (
              <div>
                <Button disabled={connect.isPending} onClick={() => connect.mutate()}>
                  {t("automation.connectMock")}
                </Button>
              </div>
            ) : (
              <p className="text-sm text-slate-600">{t("automation.ownerOnly")}</p>
            )}
            {connect.error ? <ErrorMessage error={connect.error} /> : null}
          </>
        )}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">{t("automation.policies")}</h2>
        <p className="text-sm text-slate-600">{t("automation.intro")}</p>
        {automation.isError ? <ErrorMessage error={automation.error} /> : null}
        {automation.data ? (
          <ul className="flex flex-col gap-3">
            {automation.data.items.map((item) => (
              <li key={item.action_class} className="flex flex-wrap items-center justify-between gap-2">
                <label htmlFor={`mode-${item.action_class}`} className="font-medium">
                  {t(`automation.class.${item.action_class.replace(".", "_")}`)}
                </label>
                <select
                  id={`mode-${item.action_class}`}
                  value={edits[item.action_class] ?? item.mode}
                  disabled={!owner}
                  onChange={(event) =>
                    setEdits((current) => ({ ...current, [item.action_class]: event.target.value as Mode }))
                  }
                  className="min-h-11 rounded-lg border border-slate-300 bg-white px-3"
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
          <p className="text-sm text-amber-900">{t("automation.autoNeedsReady")}</p>
        ) : null}
        {automation.data?.reviewed_at ? (
          <p className="text-sm text-slate-600">{t("automation.reviewed")}</p>
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
          <p className="text-sm text-slate-600">{t("automation.ownerOnly")}</p>
        )}
        {save.isSuccess ? <p role="status">{t("automation.saved")}</p> : null}
        {save.error ? <ErrorMessage error={save.error} /> : null}
        {owner && automation.data && !automation.data.reviewed_at ? (
          <div className="flex flex-col gap-2 border-t border-slate-200 pt-3">
            <p className="text-sm text-slate-600">{t("automation.reviewHint")}</p>
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
