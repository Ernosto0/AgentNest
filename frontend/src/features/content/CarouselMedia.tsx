import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useMediaPreview, usePatchContent, useUploadMedia } from "./hooks";
import { UploadError } from "./MediaUpload";
import { append, CAROUSEL_MAX, move, remove, sameOrder } from "./carousel";

function Thumbnail({ ws, id, deleted }: { ws: string; id: string; deleted: boolean }) {
  const { t } = useTranslation();
  const preview = useMediaPreview(ws, deleted ? null : id);
  return deleted ? <p>{t("content.media.deleted")}</p> : preview.url ?
    <img src={preview.url} alt={t("content.media.previewAlt")} className="size-20 shrink-0 rounded-control object-cover" /> :
    <p className="text-xs">{t(preview.error ? "content.media.previewFailed" : "content.media.loadingPreview")}</p>;
}

export function CarouselMedia({ item, workspaceId, disabled = false, onBusyChange }: {
  item: ContentItem; workspaceId: string; disabled?: boolean; onBusyChange?: (busy: boolean) => void;
}) {
  const { t } = useTranslation();
  const inputId = useId();
  const patch = usePatchContent(workspaceId, item.id);
  const upload = useUploadMedia(workspaceId);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<{ name: string; state: string; error?: unknown }[]>([]);
  const [announcement, setAnnouncement] = useState("");
  const dragFrom = useRef<number | null>(null);
  const ids = (item.media_items ?? []).map((m) => m.media_asset_id);
  const busy = disabled || uploading || patch.isPending;

  const save = async (next: string[], version = item.version, current = ids) => {
    if (sameOrder(current, next)) return null;
    return patch.mutateAsync({ expectedVersion: version, changes: { media_asset_ids: next } });
  };
  const reorder = async (from: number, to: number) => {
    if (busy || sameOrder(ids, move(ids, from, to))) return;
    onBusyChange?.(true);
    try {
      await save(move(ids, from, to));
      setAnnouncement(t("content.carousel.moved", { from: from + 1, to: to + 1 }));
    } catch { /* The mutation error is displayed below. */ }
    finally { onBusyChange?.(false); }
  };
  const choose = async (files: File[]) => {
    if (busy) return;
    const accepted = files.slice(0, Math.max(0, CAROUSEL_MAX - ids.length));
    setAnnouncement(files.length > accepted.length ? t("content.carousel.cap") : "");
    setProgress(accepted.map((file) => ({ name: file.name, state: "waiting" })));
    setUploading(true); onBusyChange?.(true);
    let current = ids;
    let version = item.version;
    for (const [index, file] of accepted.entries()) {
      setProgress((rows) => rows.map((row, i) => i === index ? { ...row, state: "uploading" } : row));
      let attaching = false;
      try {
        const asset = await upload.mutateAsync(file);
        attaching = true;
        const next = append(current, [asset.id]);
        const updated = await save(next, version, current);
        if (updated) { current = (updated.media_items ?? []).map((m) => m.media_asset_id); version = updated.version; }
        setProgress((rows) => rows.map((row, i) => i === index ? { ...row, state: "done" } : row));
      } catch (error) {
        setProgress((rows) => rows.map((row, i) => i === index ? { ...row, state: "error", error } : row));
        // A PATCH failure can mean a newer version exists: don't overwrite it with the old list.
        if (attaching) break;
      }
    }
    setUploading(false); onBusyChange?.(false);
  };

  return <section className="flex min-w-0 flex-col gap-3" aria-label={t("content.type.feed_carousel")}>
    <p className="text-sm text-secondary">{t("content.carousel.captionHint")}</p>
    <ol className="flex min-w-0 flex-col gap-3">
      {(item.media_items ?? []).map((media, index) => <li key={media.media_asset_id} draggable={!busy}
        onDragStart={() => { dragFrom.current = index; }} onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => { event.preventDefault(); if (dragFrom.current !== null) void reorder(dragFrom.current, index); dragFrom.current = null; }}
        className="flex min-w-0 flex-wrap items-center gap-2 rounded-control border border-border p-2">
        <span className="font-semibold">{index + 1}</span>
        <Thumbnail ws={workspaceId} id={media.media_asset_id} deleted={media.media_deleted} />
        <div className="flex flex-wrap gap-1">
          <Button variant="secondary" disabled={busy || index === 0} aria-label={t("content.carousel.up", { n: index + 1 })} onClick={() => void reorder(index, index - 1)}>↑</Button>
          <Button variant="secondary" disabled={busy || index === ids.length - 1} aria-label={t("content.carousel.down", { n: index + 1 })} onClick={() => void reorder(index, index + 1)}>↓</Button>
          <Button variant="ghost" disabled={busy} aria-label={t("content.carousel.remove", { n: index + 1 })} onClick={async () => {
            onBusyChange?.(true); try { await save(remove(ids, index)); } catch { /* Displayed below. */ } finally { onBusyChange?.(false); }
          }}>{t("content.carousel.removeShort")}</Button>
        </div>
      </li>)}
    </ol>
    <div>
      <input id={inputId} type="file" multiple accept="image/jpeg,image/png" disabled={busy || ids.length >= CAROUSEL_MAX}
        className="peer sr-only"
        onChange={(event) => { const files = Array.from(event.target.files ?? []); event.target.value = ""; void choose(files); }} />
      <label htmlFor={inputId} className="inline-flex min-h-11 cursor-pointer items-center rounded-control border border-control bg-surface px-4 py-2 text-form font-medium peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus peer-disabled:cursor-not-allowed peer-disabled:opacity-60">{t("content.carousel.upload")}</label>
    </div>
    {ids.length >= CAROUSEL_MAX ? <p>{t("content.carousel.cap")}</p> : null}
    <ul>{progress.map((row, i) => <li key={i} className="break-all text-sm">{row.name}: {t(`content.carousel.${row.state}`)}{row.error ? <UploadError error={row.error} /> : null}</li>)}</ul>
    {patch.isPending ? <p role="status">{t("content.carousel.saving")}</p> : null}
    {patch.error ? <ErrorMessage error={patch.error} /> : null}
    <p aria-live="polite" className="text-sm">{announcement}</p>
  </section>;
}
