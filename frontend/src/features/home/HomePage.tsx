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

export function HomePage() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const me = useMe();
  const [generateSheet, setGenerateSheet] = useState<{
    mode: NewContentMode;
    type?: "feed_image" | "story_image";
  } | null>(null);

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
        context={
          <div className="mb-2 flex flex-wrap items-center gap-2 text-metadata text-secondary">
            <span>{formattedDate}</span>
            {workspace.is_demo ? <SimulatedBadge /> : null}
          </div>
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={() => setGenerateSheet({ mode: "ai" })}
              className="gap-2 shadow-xs"
            >
              <SparkIcon className="text-base text-on-action" />
              <span>{t("home.quick.generate")}</span>
            </Button>
            <Button
              variant="secondary"
              onClick={() => setGenerateSheet({ mode: "blank", type: "feed_image" })}
              className="gap-1.5 shadow-xs"
            >
              <PlusIcon className="text-base" />
              <span>{t("home.quick.newPost")}</span>
            </Button>
            <Button
              variant="secondary"
              onClick={() => setGenerateSheet({ mode: "blank", type: "story_image" })}
              className="gap-1.5 shadow-xs"
            >
              <PlusIcon className="text-base" />
              <span>{t("home.quick.newStory")}</span>
            </Button>
          </div>
        }
      />

      <Dashboard />

      {generateSheet ? (
        <GenerateSheet
          initialMode={generateSheet.mode}
          initialType={generateSheet.type}
          onClose={() => setGenerateSheet(null)}
        />
      ) : null}
    </div>
  );
}
