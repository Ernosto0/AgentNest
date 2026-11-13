import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { Notice } from "@/components/Feedback";
import { PageHeader } from "@/components/Layout";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AccountSection } from "./AccountSection";
import { SecuritySection } from "./AccountSecurity";
import { ConnectionsSection } from "./ConnectionsSection";
import { PrivacySection } from "./PrivacySection";
import { SectionNav } from "./SettingsParts";
import { WorkspaceSection } from "./WorkspaceSection";

/**
 * One settings page in five groups (account, workspace, security, connections, privacy and data),
 * with in-page navigation. Larger tools (connections, team, system health) keep their own pages.
 */
export function SettingsPage() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const { hash } = useLocation();

  const sections = useMemo(
    () => [
      { id: "account", label: t("settings.nav.account") },
      { id: "workspace", label: t("settings.nav.workspace") },
      { id: "security", label: t("settings.nav.security") },
      { id: "connections", label: t("settings.nav.connections") },
      { id: "privacy", label: t("settings.nav.privacy") },
    ],
    [t],
  );

  // Deep links (e.g. the deletion email's "#danger-zone") land on their section once rendered.
  useEffect(() => {
    if (!hash) return;
    const target = document.getElementById(decodeURIComponent(hash.slice(1)));
    target?.scrollIntoView?.({ block: "start" });
    // Only on arrival: in-page navigation scrolls by itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader title={t("settings.title")} description={t("settings.description")} />

      {workspace.status === "deleting" ? (
        <Notice tone="attention" title={t("settings.deletingBanner.title")}>
          {role === "owner" ? (
            <a href="#danger-zone" className="font-semibold underline underline-offset-2">
              {t("settings.deletingBanner.owner")}
            </a>
          ) : (
            t("settings.deletingBanner.others")
          )}
        </Notice>
      ) : null}

      <div className="grid min-w-0 gap-6 lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-10">
        <SectionNav sections={sections} />
        <div className="flex min-w-0 max-w-[52rem] flex-col gap-10 pb-6">
          <AccountSection />
          <WorkspaceSection />
          <SecuritySection />
          <ConnectionsSection />
          <PrivacySection />
        </div>
      </div>
    </div>
  );
}
