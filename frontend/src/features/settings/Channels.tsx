import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChannelLinkCode } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CheckIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import {
  useChannelLinks,
  useGenerateChannelLinkCode,
  useLocalTime,
  useUnlinkChannel,
} from "./hooks";

function LinkCodeModal({
  codeData,
  onClose,
  onRegenerate,
  isRegenerating,
}: {
  codeData: ChannelLinkCode;
  onClose: () => void;
  onRegenerate: () => void;
  isRegenerating: boolean;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const expiryTime = new Date(codeData.expires_at).getTime();
  const secondsLeft = Math.max(0, Math.floor((expiryTime - now) / 1000));
  const isExpired = secondsLeft <= 0;

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const timeFormatted = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;

  const botName = codeData.bot_username?.replace(/^@/, "") || "AgentNestBot";
  const deepLink =
    codeData.deep_link_url || `https://t.me/${botName}?start=${codeData.code}`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeData.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore clipboard error in non-secure test contexts
    }
  };

  return (
    <BottomSheet
      title={t("channels.modalTitle")}
      description={t("channels.modalDesc")}
      onClose={onClose}
      footer={
        <div className="flex w-full flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t("channels.close")}
          </Button>
          {!isExpired ? (
            <a
              href={deepLink}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center justify-center rounded-control bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover focus-visible:outline-2 focus-visible:outline-focus"
            >
              {t("channels.openInTelegram")}
            </a>
          ) : null}
        </div>
      }
    >
      <div className="flex flex-col gap-5 py-2">
        {/* Code display & Copy */}
        <div className="flex flex-col items-center justify-center gap-3 rounded-panel border border-border bg-surface-subtle p-5">
          <span className="text-xs font-medium text-secondary">
            {t("channels.codeLabel")}
          </span>
          <span
            data-testid="channel-link-code-display"
            className="font-mono text-3xl font-bold tracking-widest text-primary"
          >
            {codeData.code}
          </span>
          <Button
            variant="secondary"
            onClick={handleCopy}
            className="mt-1"
          >
            {copied ? t("channels.copied") : t("channels.copyCode")}
          </Button>
        </div>

        {/* Timer / Expiry */}
        <div className="flex items-center justify-center text-sm">
          {isExpired ? (
            <div className="flex flex-col items-center gap-2">
              <span className="font-medium text-danger">
                {t("channels.codeExpired")}
              </span>
              <Button
                variant="secondary"
                disabled={isRegenerating}
                onClick={onRegenerate}
              >
                {t("channels.generateNewCode")}
              </Button>
            </div>
          ) : (
            <span
              data-testid="channel-link-timer"
              className="font-mono text-secondary"
            >
              {t("channels.expiresIn", { time: timeFormatted })}
            </span>
          )}
        </div>

        {/* Step-by-step instructions */}
        <div className="flex flex-col gap-2 rounded-panel border border-border/60 bg-surface p-4 text-sm text-secondary">
          <p className="font-medium text-primary">
            {t("channels.step1", { bot: botName })}
          </p>
          <p className="font-medium text-primary">
            {t("channels.step2", { code: codeData.code })}
          </p>
        </div>
      </div>
    </BottomSheet>
  );
}

export function Channels() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const links = useChannelLinks(workspace.id);
  const generateCode = useGenerateChannelLinkCode(workspace.id);
  const unlink = useUnlinkChannel(workspace.id);

  const [codeData, setCodeData] = useState<ChannelLinkCode | null>(null);
  const [showDisconnectDialog, setShowDisconnectDialog] = useState(false);

  const activeLink =
    links.data?.find((l) => l.channel === "telegram" && l.status === "active") ??
    null;
  const formatTime = useLocalTime();

  const handleOpenConnect = () => {
    generateCode.mutate(undefined, {
      onSuccess: (data) => setCodeData(data),
    });
  };

  const handleRegenerate = () => {
    generateCode.mutate(undefined, {
      onSuccess: (data) => setCodeData(data),
    });
  };

  const handleConfirmDisconnect = () => {
    if (!activeLink) return;
    unlink.mutate(activeLink.id, {
      onSuccess: () => setShowDisconnectDialog(false),
    });
  };

  return (
    <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-heading font-semibold text-primary">
              {t("channels.title")}
            </h2>
            <span
              data-testid="channel-status-badge"
              data-status={activeLink ? "connected" : "unlinked"}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                activeLink
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-border bg-surface-subtle text-secondary"
              }`}
            >
              {activeLink ? <CheckIcon className="text-sm" /> : null}
              {activeLink ? t("channels.connected") : t("channels.unlinked")}
            </span>
          </div>
          <p className="mt-1 text-sm text-secondary">{t("channels.intro")}</p>
        </div>
      </div>

      {links.isError ? <ErrorMessage error={links.error} /> : null}
      {generateCode.isError ? <ErrorMessage error={generateCode.error} /> : null}
      {unlink.isError ? <ErrorMessage error={unlink.error} /> : null}

      {links.isPending ? (
        <p className="text-sm text-secondary">{t("common.loading")}</p>
      ) : activeLink ? (
        <div className="flex flex-col gap-4 pt-2">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-secondary">{t("channels.telegramLabel")}</p>
              <p className="mt-0.5 text-sm font-medium text-primary">
                {activeLink.channel_username
                  ? `@${activeLink.channel_username}`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-secondary">
                {t("channels.linkedAt", { time: "" }).split(":")[0]}
              </p>
              <p className="mt-0.5 text-sm text-primary">{formatTime(activeLink.linked_at)}</p>
            </div>
          </div>
          <div>
            <Button
              variant="secondary"
              onClick={() => setShowDisconnectDialog(true)}
              className="text-danger hover:bg-danger/10"
            >
              {t("channels.disconnect")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-4 pt-2">
          <p className="text-sm text-secondary">{t("channels.none")}</p>
          <div>
            <Button
              disabled={generateCode.isPending}
              onClick={handleOpenConnect}
            >
              {generateCode.isPending ? t("common.loading") : t("channels.connect")}
            </Button>
          </div>
        </div>
      )}

      {codeData ? (
        <LinkCodeModal
          codeData={codeData}
          onClose={() => setCodeData(null)}
          onRegenerate={handleRegenerate}
          isRegenerating={generateCode.isPending}
        />
      ) : null}

      {showDisconnectDialog ? (
        <BottomSheet
          title={t("channels.disconnectTitle")}
          description={t("channels.disconnectBody")}
          onClose={() => {
            if (!unlink.isPending) setShowDisconnectDialog(false);
          }}
          footer={
            <div className="flex w-full flex-wrap justify-end gap-2">
              <Button
                variant="secondary"
                disabled={unlink.isPending}
                onClick={() => setShowDisconnectDialog(false)}
              >
                {t("channels.disconnectCancel")}
              </Button>
              <Button
                variant="danger"
                disabled={unlink.isPending}
                onClick={handleConfirmDisconnect}
              >
                {unlink.isPending
                  ? t("common.loading")
                  : t("channels.disconnectConfirm")}
              </Button>
            </div>
          }
        >
          <p className="py-2 text-sm text-secondary">
            {t("channels.disconnectBody")}
          </p>
        </BottomSheet>
      ) : null}
    </div>
  );
}
