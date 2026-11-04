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
      <header className="flex flex-col gap-4 rounded-2xl border border-border/80 bg-surface p-5 shadow-xs sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="type-page text-primary tracking-tight">
              {t("home.welcome", { name: me.data?.user.display_name ?? "" })}
            </h1>
            {workspace.is_demo ? <SimulatedBadge /> : null}
          </div>
          <p className="flex flex-wrap items-center gap-2 text-body text-secondary">
            <span className="font-medium">{formattedDate}</span>
            <span className="text-secondary/40">·</span>
            <span className="font-semibold text-primary">{workspace.name}</span>
          </p>
        </div>
        <div>
          <Link
            to={`/w/${workspace.id}/content?tab=drafts`}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-action px-5 py-2.5 text-form font-semibold text-on-action shadow-xs transition-all hover:bg-action-hover hover:shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-[0.98]"
          >
            <PlusIcon className="text-lg" />
            <span>{t("home.createContent")}</span>
          </Link>
        </div>
      </header>

      <CommandBar />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-8 flex flex-col gap-6">
          <Dashboard />
        </div>
        <div className="lg:col-span-4 flex flex-col gap-6">
          <ReadinessCard />
        </div>
      </div>
    </div>
  );
}
