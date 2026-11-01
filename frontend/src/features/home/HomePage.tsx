import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PlusIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMe } from "@/features/auth/hooks";
import { CommandBar } from "@/features/commands/CommandBar";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { Dashboard } from "./Dashboard";
import { ReadinessCard } from "./ReadinessCard";

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
    <div className="flex flex-col gap-6 pb-28 md:pb-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            {t("home.welcome", { name: me.data?.user.display_name ?? "" })}
          </h1>
          <p className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <span>{formattedDate}</span>
            <span>·</span>
            <span className="font-medium text-slate-800">{workspace.name}</span>
            {workspace.is_demo ? <SimulatedBadge /> : null}
          </p>
        </div>
        <div>
          <Link
            to={`/w/${workspace.id}/content?tab=drafts`}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-xs hover:bg-indigo-700 focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            <PlusIcon className="text-lg" />
            <span>{t("home.createContent")}</span>
          </Link>
        </div>
      </header>

      <CommandBar />

      <Dashboard />

      <ReadinessCard />
    </div>
  );
}
