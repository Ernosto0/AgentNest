import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/Layout";
import { PlusIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMe } from "@/features/auth/hooks";
import { GenerateSheet, type NewContentMode } from "@/features/content/GenerateSheet";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { Dashboard } from "./Dashboard";

type Sheet = { mode: NewContentMode; type?: "feed_image" | "story_image" };

export function HomePage() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const me = useMe();
  // One content sheet for the whole page: header actions and dashboard shortcuts share it.
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const create = (mode: NewContentMode, type?: Sheet["type"]) => setSheet({ mode, type });

  const formattedDate = new Date().toLocaleDateString(i18n.language, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: workspace.timezone,
  });

  return (
    <div className="flex flex-col gap-6 pb-4">
      <PageHeader
        title={t("home.welcome", { name: me.data?.user.display_name ?? "" })}
        description={t("home.subtitle")}
        context={
          <div className="mb-1.5 flex flex-wrap items-center gap-2 text-metadata font-medium text-secondary">
            <span className="first-letter:uppercase">{formattedDate}</span>
            {workspace.is_demo ? <SimulatedBadge compact /> : null}
          </div>
        }
        action={
          <>
            <Button onClick={() => create("ai")}>
              <SparkIcon className="text-base" />
              <span>{t("home.quick.generate")}</span>
            </Button>
            <Button variant="secondary" onClick={() => create("blank", "feed_image")} className="px-3.5">
              <PlusIcon className="text-base" />
              <span>{t("home.quick.newPost")}</span>
            </Button>
            <Button variant="secondary" onClick={() => create("blank", "story_image")} className="px-3.5">
              <PlusIcon className="text-base" />
              <span>{t("home.quick.newStory")}</span>
            </Button>
          </>
        }
      />

      <Dashboard onCreate={create} />

      {sheet ? <GenerateSheet initialMode={sheet.mode} initialType={sheet.type} onClose={() => setSheet(null)} /> : null}
    </div>
  );
}
