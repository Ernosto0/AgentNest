import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/Layout";
import { PlusIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMe } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { Dashboard } from "./Dashboard";

export function HomePage() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const me = useMe();

  const formattedDate = new Date().toLocaleDateString(i18n.language, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: workspace.timezone,
  });

  return (
    <div className="flex flex-col gap-6 pb-4">
      <PageHeader
        title={t("home.welcome", { name: me.data?.user.display_name ?? "" })}
        context={<div className="mb-2 flex flex-wrap items-center gap-2 text-metadata text-secondary"><span>{formattedDate}</span>{workspace.is_demo ? <SimulatedBadge /> : null}</div>}
        action={<Link to={`/w/${workspace.id}/content?tab=drafts`} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-control border border-control bg-surface px-4 py-2 text-body font-semibold text-action hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"><PlusIcon />{t("home.createContent")}</Link>}
      />

      <Dashboard />
    </div>
  );
}
