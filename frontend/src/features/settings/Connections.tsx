import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { capabilityLabel } from "@/features/content/messages";
import { useMeta } from "@/features/auth/hooks";
import { useConnectMock, useReconnectMock, useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AccountStatusBadge } from "./AccountStatusBadge";
import { Channels } from "./Channels";
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
  const isError = status === "error";

  return (
    <div
      data-testid="oauth-banner"
      role={isError ? "alert" : "status"}
      className={`flex flex-col gap-3 rounded-panel border p-4 ${
        isError
          ? "border-danger/30 bg-danger/10 text-danger-foreground"
          : "border-success/30 bg-success/10 text-success-foreground"
      }`}
    >
      <div className="flex flex-col gap-1">
        <p className="font-medium">{status === "connected" ? t("connections.oauthConnected") : error.what}</p>
        {isError && error.next ? <p className="text-sm opacity-90">{error.next}</p> : null}
      </div>
      <div>
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
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-heading font-semibold text-primary">{t("connections.title")}</h1>
        <p className="mt-1 text-sm text-secondary">{t("connections.intro")}</p>
      </div>

      <OAuthBanner />
      {meta.isError ? <ErrorMessage error={meta.error} /> : null}
      {accounts.isError ? <ErrorMessage error={accounts.error} /> : null}
      {accounts.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}

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
        <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
          <p className="text-sm text-secondary">{t("connections.none")}</p>
          {owner ? (
            <div className="flex flex-wrap gap-2">
              {metaAllowed ? (
                <Button
                  disabled={busy}
                  onClick={() =>
                    instagram.mutate(
                      { purpose: "connect" },
                      {
                        onSuccess: ({ authorize_url }) => {
                          setRedirecting(true);
                          window.location.assign(authorize_url);
                        },
                      },
                    )
                  }
                >
                  {t("connections.connectInstagram")}
                </Button>
              ) : null}
              {mockAllowed ? (
                <Button disabled={busy} onClick={() => connect.mutate()}>
                  {t("connections.connectMock")}
                </Button>
              ) : null}
              {meta.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
              {meta.data && !mockAllowed && !metaAllowed ? (
                <p className="text-sm text-secondary">{t("connections.unavailable")}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-secondary">{t("connections.ownerOnly")}</p>
          )}
          {connect.error ? <ErrorMessage error={connect.error} /> : null}
          {instagram.error ? <ErrorMessage error={instagram.error} /> : null}
        </div>
      ) : null}

      <Channels />
    </div>
  );
}

function AccountCard({
  account,
  owner,
  mockAllowed,
  metaAllowed,
}: {
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
    <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-heading font-semibold text-primary">
          @{account.username ?? account.id}
        </h2>
        <AccountStatusBadge status={account.status} />
        {account.is_simulated ? <SimulatedBadge /> : null}
      </div>

      {account.status === "degraded" && account.degraded_until ? (
        <p data-testid="degraded-until" className="text-sm font-medium text-warning">
          {t("connections.degradedUntil", {
            time: localTime(account.degraded_until),
          })}
        </p>
      ) : null}

      <div className="flex flex-col gap-1">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-secondary">
          {t("connections.lastError")}
        </h3>
        {account.last_error_code ? (
          <div data-testid="account-last-error" className="text-sm">
            <p className="font-medium text-primary">
              {cause.what !== "" ? cause.what : t("connections.lastErrorUnknown")}
            </p>
            {cause.next !== "" ? <p className="text-secondary">{cause.next}</p> : null}
          </div>
        ) : (
          <p className="text-sm text-secondary" data-testid="account-last-error">
            {t("connections.noError")}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-secondary">
          {t("connections.capabilities")}
        </h3>
        <p data-testid="account-capabilities" className="text-sm text-primary">
          {capabilities || "–"}
        </p>
      </div>

      {canReconnect ? (
        owner ? (
          account.provider_kind === "mock" ? (
            <div className="flex flex-col gap-2">
              <p className="text-sm text-secondary">{t("connections.reconnectHint")}</p>
              <div>
                <Button disabled={busy || !mockAllowed} onClick={() => reconnect.mutate(account.id)}>
                  {t("connections.reconnect")}
                </Button>
              </div>
            </div>
          ) : (
            <div>
              <Button
                disabled={busy || !metaAllowed}
                onClick={() =>
                  instagram.mutate(
                    { purpose: "reconnect", social_account_id: account.id },
                    {
                      onSuccess: ({ authorize_url }) => {
                        setRedirecting(true);
                        window.location.assign(authorize_url);
                      },
                    },
                  )
                }
              >
                {t("connections.reconnectInstagram")}
              </Button>
            </div>
          )
        ) : (
          <p className="text-sm text-secondary">{t("connections.ownerOnly")}</p>
        )
      ) : null}
      {reconnect.error ? <ErrorMessage error={reconnect.error} /> : null}
      {instagram.error ? <ErrorMessage error={instagram.error} /> : null}

      {owner ? (
        <div className="border-t border-border pt-4">
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
          className="text-sm font-medium text-brand hover:underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-focus"
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
                  disconnect.mutate(
                    { accountId: account.id, deleteConversationData },
                    {
                      onSuccess: close,
                    },
                  )
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
          <div className="flex flex-col gap-3">
            <p className="text-sm text-primary">{t("connections.disconnectBody")}</p>
            {disconnect.error ? <ErrorMessage error={disconnect.error} /> : null}
            <label className="mt-2 flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={deleteConversationData}
                disabled={disconnect.isPending}
                onChange={(event) => setDeleteConversationData(event.target.checked)}
                className="mt-0.5 rounded border-border text-brand focus:ring-focus"
              />
              <span className="text-sm font-medium text-primary">
                {t("connections.deleteConversationData")}
              </span>
            </label>
            <p className="text-xs text-secondary leading-relaxed">
              {t("connections.deleteConversationDataHint")}
            </p>
          </div>
        </BottomSheet>
      ) : null}
    </div>
  );
}
