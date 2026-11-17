import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Extraction } from "@/api/types";
import { InstagramImportControl } from "./InstagramImportButton";
import { WebsiteImportForm } from "./WebsiteImportForm";

export function ProfileImport({ workspaceId, showInstagram = true, onDone }: {
  workspaceId: string;
  showInstagram?: boolean;
  onDone?: (run: Extraction) => void;
}) {
  const { t } = useTranslation();
  const [hasSuggestions, setHasSuggestions] = useState(false);
  function done(run: Extraction) {
    if (run.status === "succeeded" && run.candidates_created > 0) setHasSuggestions(true);
    onDone?.(run);
  }
  return <section className="flex min-w-0 flex-col gap-3 [overflow-wrap:anywhere]">
    <h3 className="text-body font-semibold">{t("knowledge.importProfile.title")}</h3>
    <p className="text-metadata text-secondary">{t("knowledge.importProfile.intro")}</p>
    {showInstagram ? <InstagramImportControl key={`instagram-${workspaceId}`} workspaceId={workspaceId} variant="secondary" onDone={done} /> : null}
    <WebsiteImportForm key={workspaceId} workspaceId={workspaceId} variant="secondary" onDone={done} />
    {hasSuggestions ? <Link to={`/w/${workspaceId}/more/knowledge/suggestions`}
      className="inline-flex min-h-11 items-center justify-center self-start rounded-control bg-action px-4 py-2 text-body font-semibold text-on-action hover:bg-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{t("knowledge.importProfile.review")}</Link> : null}
  </section>;
}
