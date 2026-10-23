import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { capabilityLabel } from "@/features/content/messages";
import { useMeta } from "@/features/auth/hooks";
import { useConnectMock, useReconnectMock, useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AccountStatusBadge } from "./AccountStatusBadge";
import { useConnectInstagram, useDisconnectAccount, useErrorText, useLocalTime } from "./hooks";

// Only callback catalog codes can select text. Never reflect arbitrary provider/query strings.
const OAUTH_ERRORS = new Set([
  "ACCOUNT_MISMATCH",
  "OAUTH_STATE_INVALID",
  "ACCOUNT_NEEDS_REAUTH",
  "PROVIDER_UNAVAILABLE",
  "FORBIDDEN",
  "CONFLICT_STATE",
  "CAPABILITY_MISSING",
]);

function OAuthBanner() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const errorText = useErrorText();
  const status = params.get("oauth");
  if (status !== "connected" && status !== "error") return null;
  const code = params.get("code") ?? "";
  const error = errorText(OAUTH_ERRORS.has(code) ? code : "UNKNOWN");
  return (
    <div
      data-testid="oauth-banner"
      role={status === "error" ? "alert" : "status"}
      className="rounded-lg bg-slate-100 p-3"
    >
      <p>{status === "connected" ? t("connections.oauthConnected") : error.what}</p>
      {status === "error" ? <p>{error.next}</p> : null}
      <Button
        variant="secondary"
        onClick={() => {
          const next = new URLSearchParams(params);
          next.delete("oauth");
          next.delete("code");
          setParams(next, { replace: true });
        }}
      >
        {t("connections.dismiss")}
      </Button>
    </div>
  );
}

/** The Instagram connection: its status, the last error in plain language, and what it can do. */
export function Connections() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const owner = role === "owner";
  const accounts = useSocialAccounts(workspace.id);
  const connect = useConnectMock(workspace.id);
  const instagram = useConnectInstagram(workspace.id);
  const meta = useMeta();
  const mockAllowed =
    meta.data?.instagram_providers?.includes("mock") === true &&
    (!meta.data.mock_requires_demo_workspace || workspace.is_demo);
  const metaAllowed = meta.data?.instagram_providers?.includes("meta") === true;
  const [redirecting, setRedirecting] = useState(false);
  const busy = connect.isPending || instagram.isPending || redirecting;
  const account = accounts.data?.find((a) => a.status !== "disconnected") ?? null;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("connections.title")}</h1>
        <p className="mt-1 text-slate-600">{t("connections.intro")}</p>
      </div>

      <OAuthBanner />
      {meta.isError ? <ErrorMessage error={meta.error} /> : null}
      {accounts.isError ? <ErrorMessage error={accounts.error} /> : null}
      {accounts.isPending ? <p>{t("common.loading")}</p> : null}

      {accounts.data && account ? (
        <AccountCard
          key={account.id}
          account={account}
          owner={owner}
          mockAllowed={mockAllowed}
          metaAllowed={metaAllowed}
        />
      ) : null}

      {accounts.data && !account ? (
        <Card className="flex flex-col gap-3">
          <p>{t("connections.none")}</p>
          {owner ? (
            <div className="flex flex-wrap gap-2">
              {metaAllowed ? (
                <Button
                  disabled={busy}
                  onClick={() => instagram.mutate({ purpose: "connect" }, {
                    onSuccess: ({ authorize_url }) => {
                      setRedirecting(true);
                      window.location.assign(authorize_url);
                    },
                  })}
                >
                  {t("connections.connectInstagram")}
                </Button>
              ) : null}
              {mockAllowed ? (
                <Button disabled={busy} onClick={() => connect.mutate()}>
                  {t("connections.connectMock")}
                </Button>
              ) : null}
              {meta.isPending ? <p>{t("common.loading")}</p> : null}
              {meta.data && !mockAllowed && !metaAllowed ? <p>{t("connections.unavailable")}</p> : null}
            </div>
          ) : (
            <p className="text-sm text-slate-600">{t("connections.ownerOnly")}</p>
          )}
          {connect.error ? <ErrorMessage error={connect.error} /> : null}
          {instagram.error ? <ErrorMessage error={instagram.error} /> : null}
        </Card>
      ) : null}
    </div>
  );
}

function AccountCard({ account, owner, mockAllowed, metaAllowed }: {
  account: SocialAccount;
  owner: boolean;
  mockAllowed: boolean;
  metaAllowed: boolean;
}) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const reconnect = useReconnectMock(workspace.id);
  const disconnect = useDisconnectAccount(workspace.id);
  const instagram = useConnectInstagram(workspace.id);
  const errorText = useErrorText();
  const localTime = useLocalTime();
  const [confirming, setConfirming] = useState(false);
  const [deleteConversationData, setDeleteConversationData] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const busy = reconnect.isPending || instagram.isPending || disconnect.isPending || redirecting;
  const close = () => {
    setConfirming(false);
    setDeleteConversationData(false);
  };

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
                <Button disabled={busy || !mockAllowed} onClick={() => reconnect.mutate(account.id)}>
                  {t("connections.reconnect")}
                </Button>
              </div>
            </div>
          ) : (
            <Button
              disabled={busy || !metaAllowed}
              onClick={() => instagram.mutate(
                { purpose: "reconnect", social_account_id: account.id },
                {
                  onSuccess: ({ authorize_url }) => {
                    setRedirecting(true);
                    window.location.assign(authorize_url);
                  },
                },
              )}
            >
              {t("connections.reconnectInstagram")}
            </Button>
          )
        ) : (
          <p className="text-sm text-slate-600">{t("connections.ownerOnly")}</p>
        )
      ) : null}
      {reconnect.error ? <ErrorMessage error={reconnect.error} /> : null}
      {instagram.error ? <ErrorMessage error={instagram.error} /> : null}

      {owner ? (
        <div className="border-t border-slate-200 pt-3">
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => {
              disconnect.reset();
              setDeleteConversationData(false);
              setConfirming(true);
            }}
          >
            {t("connections.disconnect")}
          </Button>
        </div>
      ) : null}
      {disconnect.error && !confirming ? <ErrorMessage error={disconnect.error} /> : null}

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
          onClose={() => {
            if (!disconnect.isPending) close();
          }}
          footer={
            <div className="flex flex-wrap gap-2">
              <Button
                variant="danger"
                disabled={busy}
                onClick={() =>
                  disconnect.mutate({ accountId: account.id, deleteConversationData }, {
                    onSuccess: close,
                  })
                }
              >
                {t("connections.disconnectConfirm")}
              </Button>
              <Button variant="secondary" disabled={disconnect.isPending} onClick={close}>
                {t("connections.disconnectCancel")}
              </Button>
            </div>
          }
        >
          <p>{t("connections.disconnectBody")}</p>
          {disconnect.error ? <ErrorMessage error={disconnect.error} /> : null}
          <label className="mt-4 flex items-start gap-2">
            <input
              type="checkbox"
              checked={deleteConversationData}
              disabled={disconnect.isPending}
              onChange={(event) => setDeleteConversationData(event.target.checked)}
            />
            {t("connections.deleteConversationData")}
          </label>
          <p className="mt-2 text-sm text-slate-600">{t("connections.deleteConversationDataHint")}</p>
        </BottomSheet>
      ) : null}
    </Card>
  );
}
