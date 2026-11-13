import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChatIcon, LinkIcon, ShieldCheckIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS, SettingRow, SettingsPanel, SettingsSection } from "./SettingsParts";
import { WorkspaceDangerZone } from "./WorkspaceDangerZone";

const ROW_LINK = `inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-control px-2.5 text-body font-semibold text-action hover:bg-surface-subtle sm:min-h-10 ${FOCUS}`;

/**
 * What the product actually offers for customer data, and where: per-conversation export and
 * erasure (owner, Inbox), optional data removal when disconnecting Instagram, the public policy,
 * and (owner only) workspace deletion.
 */
export function PrivacySection() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const isOwner = role === "owner"; // data.export, data.delete, workspace.manage

  return (
    <SettingsSection id="privacy" title={t("settings.nav.privacy")} description={t("settings.privacy.description")}>
      <SettingsPanel>
        <SettingRow
          className="border-t-0"
          label={
            <span className="inline-flex items-center gap-2">
              <ChatIcon aria-hidden="true" className="text-action" />
              {t("settings.privacy.conversationsTitle")}
            </span>
          }
          description={isOwner ? t("settings.privacy.conversationsOwner") : t("settings.privacy.conversationsOthers")}
        >
          <Link to={`/w/${workspace.id}/inbox`} className={ROW_LINK}>
            {t("settings.privacy.openInbox")}
          </Link>
        </SettingRow>
        <SettingRow
          label={
            <span className="inline-flex items-center gap-2">
              <LinkIcon aria-hidden="true" className="text-action" />
              {t("settings.privacy.disconnectTitle")}
            </span>
          }
          description={t("settings.privacy.disconnectBody")}
        >
          <Link to={`/w/${workspace.id}/more/settings/connections`} className={ROW_LINK}>
            {t("settings.privacy.openConnections")}
          </Link>
        </SettingRow>
        <SettingRow
          label={
            <span className="inline-flex items-center gap-2">
              <ShieldCheckIcon aria-hidden="true" className="text-action" />
              {t("settings.privacy.policyTitle")}
            </span>
          }
          description={t("settings.privacy.policyBody")}
        >
          <a href="/privacy" target="_blank" rel="noopener" className={ROW_LINK}>
            {t("settings.privacy.readPolicy")}
            <span className="sr-only"> {t("settings.privacy.newTab")}</span>
          </a>
        </SettingRow>
      </SettingsPanel>

      {isOwner ? <WorkspaceDangerZone /> : null}
    </SettingsSection>
  );
}
