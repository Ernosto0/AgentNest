import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { capabilityLabel } from "@/features/content/messages";
import { useConnectMock, useReconnectMock, useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AccountStatusBadge } from "./AccountStatusBadge";
import { useDisconnectAccount, useErrorText, useLocalTime } from "./hooks";

/** The Instagram connection: its status, the last error in plain language, and what it can do. */
export function Connections() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const owner = role === "owner";
  const accounts = useSocialAccounts(workspace.id);
  const connect = useConnectMock(workspace.id);
  const account = accounts.data?.find((a) => a.status !== "disconnected") ?? null;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("connections.title")}</h1>
        <p className="mt-1 text-slate-600">{t("connections.intro")}</p>
      </div>

      {accounts.isError ? <ErrorMessage error={accounts.error} /> : null}
      {accounts.isPending ? <p>{t("common.loading")}</p> : null}

      {accounts.data && account ? <AccountCard account={account} owner={owner} /> : null}

      {accounts.data && !account ? (
        <Card className="flex flex-col gap-3">
          <p>{t("connections.none")}</p>
          {owner ? (
            <div>
              <Button disabled={connect.isPending} onClick={() => connect.mutate()}>
                {t("connections.connectMock")}
              </Button>
            </div>
          ) : (
            <p className="text-sm text-slate-600">{t("connections.ownerOnly")}</p>
          )}
          {connect.error ? <ErrorMessage error={connect.error} /> : null}
        </Card>
      ) : null}
    </div>
  );
}

function AccountCard({ account, owner }: { account: SocialAccount; owner: boolean }) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const reconnect = useReconnectMock(workspace.id);
  const disconnect = useDisconnectAccount(workspace.id);
  const errorText = useErrorText();
  const localTime = useLocalTime();
  const [confirming, setConfirming] = useState(false);

  const cause = errorText(account.last_error_code);
  const capabilities = Object.entries(account.capabilities)
    .filter(([, granted]) => granted === true)
    .map(([name]) => capabilityLabel(name, t))
    .join(", ");
  const canReconnect = account.status === "needs_reauth";

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">@{account.username ?? account.id}</h2>
        <AccountStatusBadge status={account.status} />
        {account.is_simulated ? <SimulatedBadge /> : null}
      </div>

      {account.status === "degraded" && account.degraded_until ? (
        <p data-testid="degraded-until" className="text-sm text-amber-900">
          {t("connections.degradedUntil", {
            time: localTime(account.degraded_until),
          })}
        </p>
      ) : null}

      <div>
        <h3 className="text-sm font-semibold text-slate-700">{t("connections.lastError")}</h3>
        {account.last_error_code ? (
          <div data-testid="account-last-error">
            <p>{cause.what !== "" ? cause.what : t("connections.lastErrorUnknown")}</p>
            {cause.next !== "" ? <p className="text-sm text-slate-600">{cause.next}</p> : null}
          </div>
        ) : (
          <p className="text-slate-700" data-testid="account-last-error">
            {t("connections.noError")}
          </p>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-slate-700">{t("connections.capabilities")}</h3>
        <p data-testid="account-capabilities">{capabilities || "–"}</p>
      </div>

      {canReconnect ? (
        owner ? (
          account.provider_kind === "mock" ? (
            <div className="flex flex-col gap-2">
              <p className="text-sm text-slate-600">{t("connections.reconnectHint")}</p>
              <div>
                <Button disabled={reconnect.isPending} onClick={() => reconnect.mutate(account.id)}>
                  {t("connections.reconnect")}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-600">{t("connections.reconnectReal")}</p>
          )
        ) : (
          <p className="text-sm text-slate-600">{t("connections.ownerOnly")}</p>
        )
      ) : null}
      {reconnect.error ? <ErrorMessage error={reconnect.error} /> : null}

      {owner ? (
        <div className="border-t border-slate-200 pt-3">
          <Button variant="secondary" onClick={() => setConfirming(true)}>
            {t("connections.disconnect")}
          </Button>
        </div>
      ) : null}
      {disconnect.error ? <ErrorMessage error={disconnect.error} /> : null}

      {role === "owner" || role === "manager" ? (
        <Link
          to={`/w/${workspace.id}/more/settings/system-health`}
          className="text-sm font-semibold text-indigo-700 underline underline-offset-2"
        >
          {t("settings.openSystemHealth")}
        </Link>
      ) : null}

      {confirming ? (
        <BottomSheet
          title={t("connections.disconnectTitle")}
          onClose={() => setConfirming(false)}
          footer={
            <div className="flex flex-wrap gap-2">
              <Button
                variant="danger"
                disabled={disconnect.isPending}
                onClick={() =>
                  disconnect.mutate(account.id, {
                    onSettled: () => setConfirming(false),
                  })
                }
              >
                {t("connections.disconnectConfirm")}
              </Button>
              <Button variant="secondary" onClick={() => setConfirming(false)}>
                {t("connections.disconnectCancel")}
              </Button>
            </div>
          }
        >
          <p>{t("connections.disconnectBody")}</p>
        </BottomSheet>
      ) : null}
    </Card>
  );
}
