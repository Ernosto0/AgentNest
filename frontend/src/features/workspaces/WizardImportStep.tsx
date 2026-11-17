import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { ProfileImport } from "@/features/knowledge/ProfileImport";

export function WizardImportStep({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const heading = useRef<HTMLHeadingElement>(null);
  const [hasSuggestions, setHasSuggestions] = useState(false);
  useEffect(() => { heading.current?.focus(); }, []);
  return <section className="flex min-w-0 flex-col gap-5 rounded-panel border border-border bg-surface p-5 sm:p-6" aria-labelledby="wizard-import-heading">
    <h2 id="wizard-import-heading" ref={heading} tabIndex={-1} className="type-section rounded-control focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{t("wizard.import.title")}</h2>
    <ProfileImport workspaceId={workspaceId} showInstagram={false} onDone={(run) => {
      if (run.status === "succeeded" && run.candidates_created > 0) setHasSuggestions(true);
    }} />
    <p className="text-body text-secondary [overflow-wrap:anywhere]">{t("wizard.import.instagramLater")}</p>
    <Button block variant={hasSuggestions ? "primary" : "secondary"} onClick={() => void navigate(`/w/${workspaceId}/more/knowledge${hasSuggestions ? "/suggestions" : ""}`)}>
      {t(hasSuggestions ? "wizard.import.review" : "wizard.import.skip")}
    </Button>
  </section>;
}
