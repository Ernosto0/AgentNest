import { useTranslation } from "react-i18next";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMe } from "@/features/auth/hooks";
import { CommandBar } from "@/features/commands/CommandBar";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ReadinessCard } from "./ReadinessCard";

export function HomePage() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const me = useMe();

  return (
    <div className="flex flex-col gap-5 pb-20 md:pb-0">
      <h1 className="text-2xl font-semibold">{t("home.title")}</h1>

      <CommandBar />

      <Card className="flex flex-col gap-3">
        <p className="text-lg font-medium">
          {t("home.welcome", { name: me.data?.user.display_name ?? "" })}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-slate-900">{workspace.name}</span>
          {workspace.is_demo ? <SimulatedBadge /> : null}
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-600">{t("home.yourRole")}</dt>
          <dd>{t(`workspaces.role.${role}`)}</dd>
          <dt className="text-slate-600">{t("home.timezone")}</dt>
          <dd className="min-w-0 break-words">{workspace.timezone}</dd>
          <dt className="text-slate-600">{t("home.currency")}</dt>
          <dd>{workspace.currency}</dd>
        </dl>
      </Card>

      <ReadinessCard />

      <EmptyState
        title={t("empty.comingLater")}
        description={t("empty.comingLaterHint")}
      />
    </div>
  );
}
