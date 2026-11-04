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
    <div className="flex flex-col gap-6 pb-28 md:pb-10">
      {/* Executive Command Header */}
      <header className="relative overflow-hidden rounded-2xl border border-border/90 bg-gradient-to-r from-surface via-surface to-surface-subtle/50 p-6 shadow-card-modern sm:flex-row sm:items-center sm:justify-between flex flex-col gap-5">
        <div className="absolute top-0 right-0 h-32 w-64 bg-gradient-to-bl from-emerald-500/10 via-teal-500/5 to-transparent pointer-events-none rounded-tr-2xl" />
        <div className="flex flex-col gap-2 relative z-10">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="type-page text-primary tracking-tight font-heading font-extrabold text-2xl sm:text-3xl">
              {t("home.welcome", { name: me.data?.user.display_name ?? "" })}
            </h1>
            {workspace.is_demo ? <SimulatedBadge /> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2.5 text-metadata text-secondary">
            <span className="flex items-center gap-1.5 font-medium">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              {formattedDate}
            </span>
            <span className="text-secondary/40 font-bold">·</span>
            <span className="rounded-md bg-surface-subtle px-2 py-0.5 font-semibold text-primary border border-border/60">
              {workspace.name}
            </span>
          </div>
        </div>
        <div className="relative z-10 shrink-0">
          <Link
            to={`/w/${workspace.id}/content?tab=drafts`}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-action px-5 py-2.5 text-form font-semibold text-on-action shadow-xs transition-all duration-150 hover:bg-action-hover hover:shadow-card-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-[0.98]"
          >
            <PlusIcon className="text-lg" />
            <span>{t("home.createContent")}</span>
          </Link>
        </div>
      </header>

      <CommandBar />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-8 flex flex-col gap-6 min-w-0">
          <Dashboard />
        </div>
        <div className="lg:col-span-4 flex flex-col gap-6 min-w-0">
          <ReadinessCard />
        </div>
      </div>
    </div>
  );
}
