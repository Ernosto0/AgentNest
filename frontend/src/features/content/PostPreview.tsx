import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { ImageIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useMediaPreview } from "./hooks";

export function PostPreview({ item, caption, overlay, account }: {
  item: ContentItem; caption: string; overlay: readonly string[]; account?: string;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const media = useMediaPreview(workspace.id, item.media_deleted ? null : item.media_asset_id);
  const [failed, setFailed] = useState(false);
  const story = item.content_type === "story_image";
  return <section aria-label={t("core.preview")} className="flex min-w-0 flex-col gap-3" data-testid="post-preview">
    <h2 className="type-section">{t("core.preview")}</h2>
    <p className="text-metadata text-secondary">{t("core.approximate")}</p>
    <div className="overflow-hidden rounded-panel border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 p-4"><strong className="break-all">{account ? `@${account}` : t("core.noAccount")}</strong>{item.is_simulated ? <SimulatedBadge /> : null}</div>
      <div className={`flex items-center justify-center bg-surface-subtle ${story ? "aspect-9/16 max-h-[60dvh]" : "aspect-square"}`}>
        {media.url && !failed ? <img src={media.url} onError={() => setFailed(true)} alt={t("core.postImage")} className="h-full w-full object-contain" /> : <div className="flex flex-col items-center gap-3 p-5 text-center text-secondary"><ImageIcon className="text-3xl" /><p>{item.media_deleted ? t("content.media.deleted") : failed || media.error ? t("content.media.previewFailed") : item.media_asset_id ? t("content.media.loadingPreview") : t("content.schedule.noMedia")}</p></div>}
      </div>
      {!story ? <p className="whitespace-pre-wrap break-words p-4 text-form">{caption || t("content.schedule.noCaption")}</p> : <div className="p-4"><p className="text-metadata text-secondary">{t("content.editor.overlayNote")}</p><ul className="mt-2 space-y-2">{overlay.filter(Boolean).map((line, index) => <li key={index} className="whitespace-pre-wrap break-words">{line}</li>)}</ul></div>}
    </div>
  </section>;
}
