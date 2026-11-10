import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { SparkIcon } from "@/components/icons";
import { Panel, PanelHeading } from "@/features/home/DashboardPanel";

const STEPS = ["paste", "suggest", "review"] as const;

/**
 * The paste-and-extract entry, in the assistant's own tone. It says plainly that the result is
 * suggestions the owner decides on, never facts in use.
 */
export function TeachPanel({ onPaste }: { onPaste: () => void }) {
  const { t } = useTranslation();
  return (
    <Panel tone="assistant" aria-labelledby="knowledge-teach-title" data-testid="knowledge-teach" className="gap-3">
      <PanelHeading id="knowledge-teach-title" icon={<SparkIcon />} iconTone="assistant" title={t("knowledge.teach.title")} />
      <p className="text-metadata text-primary/80">{t("knowledge.teach.body")}</p>
      <ol className="flex flex-col gap-1.5">
        {STEPS.map((step, index) => (
          <li key={step} className="flex items-center gap-2.5 text-metadata text-primary">
            <span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center rounded-full bg-surface text-[0.6875rem] font-bold text-action tabular-nums">
              {index + 1}
            </span>
            {t(`knowledge.teach.steps.${step}`)}
          </li>
        ))}
      </ol>
      <Button onClick={onPaste} data-testid="open-paste-extract" className="self-start">
        <SparkIcon className="text-base" />
        {t("extract.open")}
      </Button>
    </Panel>
  );
}
