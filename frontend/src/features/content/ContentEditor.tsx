import { useDirtyForm } from "@/components/DirtyForms";
import { PostPreview } from "./PostPreview";
import { useEffect, useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ContentIssue, ContentItem, ContentValidation } from "@/api/types";
import { AlertIcon, CheckIcon } from "@/components/icons";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { TextField } from "@/components/TextField";
import { FactChip } from "@/features/inbox/DraftParts";
import { useFacts } from "@/features/knowledge/hooks";
import { pickLabel } from "@/features/knowledge/labels";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { usePatchContent, useValidateContent, type ContentChanges } from "./hooks";
import {
  CAPTION_MAX_CHARS,
  NOTES_MAX,
  OVERLAY_ITEM_MAX,
  OVERLAY_ITEMS_MAX,
  TITLE_MAX,
} from "./limits";
import { blockingIssueMessage, checkMessage } from "./messages";
import { MediaUpload } from "./MediaUpload";
import { editVoidsApproval, isEditable } from "./status";

interface Edits {
  title?: string;
  caption?: string;
  overlay?: string[];
  notes?: string;
}

const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((v, i) => v === b[i]);

/**
 * The claim report of one text. A value that equals a verified fact (`matches_verified`) is
 * grounded: it is drawn as a fact chip and does not block. Every other issue blocks submission.
 */
function FieldIssues({ field, issues }: { field: string; issues: ContentIssue[] }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const facts = useFacts(workspace.id);
  const mine = issues.filter((issue) => issue.field === field);
  if (mine.length === 0) return null;
  const grounded = mine.filter((issue) => issue.matches_verified);
  const blocking = mine.filter((issue) => !issue.matches_verified);

  return (
    <div className="flex flex-col gap-2 pt-1" data-testid="field-issues">
      {blocking.map((issue, index) => (
        <p
          key={`${issue.code}-${index}`}
          data-testid="blocking-issue"
          data-code={issue.code}
          className="flex items-start gap-2 rounded-control bg-danger-subtle p-3 text-sm text-danger border border-danger shadow-xs"
        >
          <AlertIcon className="mt-0.5 shrink-0 text-base" />
          <span>{blockingIssueMessage(issue, t)}</span>
        </p>
      ))}
      {blocking.length > 0 ? (
        <p className="text-xs text-secondary pl-0.5">{t("content.editor.issues.blockingHint")}</p>
      ) : null}
      {grounded.map((issue, index) => {
        const fact = facts.data?.find((candidate) => candidate.key === issue.fact_key);
        return (
          <p
            key={`${issue.code}-${index}`}
            data-testid="grounded-issue"
            className="flex flex-wrap items-center gap-2 text-sm text-secondary"
          >
            <FactChip
              fact={{
                display: issue.text,
                label: fact ? pickLabel(fact.label, i18n.language) : (issue.fact_key ?? issue.text),
                version: fact?.current_version ?? null,
              }}
            />
            <span>{t("content.editor.issues.grounded", { text: issue.text })}</span>
          </p>
        );
      })}
    </div>
  );
}

function Counter({ id, count, max }: { id: string; count: number; max: number }) {
  const { t } = useTranslation();
  const over = count > max;
  return (
    <div className="flex justify-end pt-1">
      <span
        id={id}
        data-testid="caption-counter"
        className={`text-xs font-semibold tabular-nums ${over ? "text-danger" : "text-secondary"}`}
      >
        {over ? t("content.editor.counterOver", { count, max }) : t("content.editor.counter", { count, max })}
      </span>
    </div>
  );
}

/** The dry-run result: what must be fixed, what is worth a look. */
function Checks({ result }: { result: ContentValidation }) {
  const { t } = useTranslation();
  const errors = result.errors ?? [];
  // Image warnings are drawn next to the image.
  const warnings = (result.warnings ?? []).filter((w) => w.field !== "media_asset_id");
  if (errors.length === 0 && warnings.length === 0) {
    return (
      <div role="status" className="flex items-center gap-2 rounded-control bg-success-subtle p-3.5 text-sm font-semibold text-success border border-success/30 shadow-xs" data-testid="check-clean">
        <CheckIcon className="text-base" />
        <span>{t("content.editor.checkClean")}</span>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3" data-testid="checks">
      {errors.length > 0 ? (
        <div className="rounded-panel bg-danger-subtle p-4 text-sm text-danger border border-danger shadow-xs">
          <p className="font-semibold flex items-center gap-2">
            <AlertIcon className="text-base shrink-0" />
            <span>{t("content.editor.checks.errorsLabel")}</span>
          </p>
          <ul className="mt-2 list-disc pl-5 space-y-1">
            {errors.map((item, index) => (
              <li key={`${item.code}-${index}`} data-code={item.code}>
                {checkMessage(item, t)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {warnings.length > 0 ? (
        <div className="rounded-panel bg-attention-subtle p-4 text-sm text-attention border border-attention shadow-xs">
          <p className="font-semibold flex items-center gap-2">
            <AlertIcon className="text-base shrink-0" />
            <span>{t("content.editor.checks.warningsLabel")}</span>
          </p>
          <ul className="mt-2 list-disc pl-5 space-y-1">
            {warnings.map((item, index) => (
              <li key={`${item.code}-${index}`} data-code={item.code}>
                {checkMessage(item, t)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** A finished item shown as text (an item that is publishing, published or cancelled cannot change). */
function ReadOnlyText({ item }: { item: ContentItem }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4" data-testid="content-readonly">
      <p className="text-sm font-semibold text-secondary">{t("content.editor.readOnly")}</p>
      {item.media_asset_id && item.media_deleted ? (
        <p className="rounded-control bg-surface-subtle p-4 text-sm text-secondary border border-border" data-testid="media-deleted">
          {t("content.media.deleted")}
        </p>
      ) : null}
      {item.content_type === "feed_image" && item.caption ? (
        <div className="rounded-panel border border-border bg-surface-subtle/50 p-4">
          <p className="break-words whitespace-pre-wrap text-primary text-base leading-relaxed">{item.caption}</p>
        </div>
      ) : null}
      {item.content_type === "story_image" && item.overlay_text_suggestions.length > 0 ? (
        <div className="rounded-panel border border-border bg-surface-subtle/50 p-4">
          <ul className="list-disc pl-5 text-primary space-y-1.5">
            {item.overlay_text_suggestions.map((text, index) => (
              <li key={index} className="break-words whitespace-pre-wrap">
                {text}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Edit a draft: caption (feed) or overlay suggestions (story), the image, the notes. Saves only
 * the fields that changed, always with the version the user was looking at (`expected_version`).
 * If someone else saved first the server answers 409 and the latest item is loaded, with the
 * user's typing left in place.
 */
export function ContentEditor({
  item,
  onDirtyChange,
  actions,
  account,
}: {
  item: ContentItem;
  actions?: (dirty: boolean) => ReactNode;
  account?: string;
  /** Told whenever there are unsaved changes (the page holds back "schedule" until they are saved). */
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const ids = { caption: useId(), counter: useId(), notes: useId() };
  const patch = usePatchContent(workspace.id, item.id);
  const validate = useValidateContent(workspace.id, item.id);
  const [panel, setPanel] = useState("edit");
  const [edits, setEdits] = useState<Edits>({});
  const [conflict, setConflict] = useState(false);
  const [saved, setSaved] = useState(false);
  const [checks, setChecks] = useState<ContentValidation | null>(null);

  const isStory = item.content_type === "story_image";
  const title = edits.title ?? item.title;
  const caption = edits.caption ?? item.caption ?? "";
  const overlay = edits.overlay ?? item.overlay_text_suggestions;
  const notes = edits.notes ?? item.visual_notes ?? "";

  const dirty = {
    title: edits.title !== undefined && edits.title !== item.title,
    caption: edits.caption !== undefined && edits.caption !== (item.caption ?? ""),
    overlay: edits.overlay !== undefined && !sameList(edits.overlay, item.overlay_text_suggestions),
    notes: edits.notes !== undefined && edits.notes !== (item.visual_notes ?? ""),
  };
  const anyDirty = dirty.title || dirty.caption || dirty.overlay || dirty.notes;
  useDirtyForm(anyDirty);
  useEffect(() => {
    onDirtyChange?.(anyDirty || patch.isPending);
  }, [anyDirty, patch.isPending, onDirtyChange]);

  if (!isEditable(item.status)) {
    return <div className="grid min-w-0 gap-6 min-[1200px]:grid-cols-2"><ReadOnlyText item={item} /><PostPreview key={item.media_asset_id} item={item} caption={caption} overlay={overlay} account={account} /></div>;
  }

  const edit = (next: Edits) => {
    setEdits((current) => ({ ...current, ...next }));
    setSaved(false);
  };

  const save = () => {
    const changes: ContentChanges = {};
    if (dirty.title) changes.title = title.trim();
    if (dirty.caption) changes.caption = caption.trim() === "" ? null : caption;
    if (dirty.overlay) changes.overlay_text_suggestions = overlay.filter((text) => text.trim() !== "");
    if (dirty.notes) changes.visual_notes = notes.trim() === "" ? null : notes;
    setConflict(false);
    patch.mutate(
      { expectedVersion: item.version, changes },
      {
        onSuccess: () => {
          // Keep anything typed while the request was in flight.
          setEdits((current) => ({
            title: current.title === title ? undefined : current.title,
            caption: current.caption === caption ? undefined : current.caption,
            overlay: current.overlay === overlay ? undefined : current.overlay,
            notes: current.notes === notes ? undefined : current.notes,
          }));
          setChecks(null); // the last check described text that has just changed
          setSaved(true);
        },
        onError: (error) => {
          if (error.code === "VERSION_CONFLICT") setConflict(true);
        },
      },
    );
  };

  const runCheck = () => validate.mutate(undefined, { onSuccess: (result) => setChecks(result) });

  const attachMedia = (mediaId: string) => {
    setConflict(false);
    patch.mutate(
      { expectedVersion: item.version, changes: { media_asset_id: mediaId } },
      {
        onSuccess: () => {
          setSaved(true);
          runCheck(); // the aspect-ratio warning of a story arrives with the image
        },
        onError: (error) => {
          if (error.code === "VERSION_CONFLICT") setConflict(true);
        },
      },
    );
  };

  const updateOverlay = (index: number, text: string) =>
    edit({ overlay: overlay.map((current, i) => (i === index ? text : current)) });

  const mediaWarnings = (checks?.warnings ?? []).filter((w) => w.field === "media_asset_id");
  const issues = item.validation.issues;
  const busy = patch.isPending;

  return (
    <div className="flex min-w-0 flex-col gap-4">
    <div role="group" aria-label={t("core.preview")} className="flex gap-2 min-[1200px]:hidden">{["edit", "preview"].map(name => <Button key={name} variant={panel === name ? "primary" : "secondary"} aria-pressed={panel === name} onClick={() => setPanel(name)}>{t(`core.${name}`)}</Button>)}</div>
    <div className="grid min-w-0 items-start gap-6 min-[1200px]:grid-cols-[minmax(0,1fr)_minmax(280px,0.8fr)]">
    <form
      className={`min-w-0 flex-col gap-6 rounded-panel border border-border bg-surface p-4 sm:p-6 ${panel === "edit" ? "flex" : "hidden min-[1200px]:flex"}`}
      onSubmit={(event) => {
        event.preventDefault();
        if (anyDirty && title.trim() !== "") save();
      }}
    >
      {editVoidsApproval(item.status) ? (
        <div className="flex items-center gap-2 rounded-panel border border-attention bg-attention-subtle p-3.5 text-sm text-attention shadow-xs" data-testid="voids-approval">
          <AlertIcon className="text-base shrink-0" />
          <p>{t("content.editor.editVoidsApproval")}</p>
        </div>
      ) : null}

      <MediaUpload
        workspaceId={workspace.id}
        contentType={item.content_type}
        mediaId={item.media_asset_id}
        deleted={item.media_deleted}
        onUploaded={(asset) => attachMedia(asset.id)}
        warnings={mediaWarnings}
        disabled={busy}
      />

      {isStory ? (
        <fieldset className="flex flex-col gap-2.5">
          <legend className="text-sm font-semibold text-primary">{t("content.editor.overlayLabel")}</legend>
          <p className="text-xs text-secondary" data-testid="overlay-note">
            {t("content.editor.overlayNote")}
          </p>
          {overlay.map((text, index) => (
            <div key={index} className="flex flex-col gap-1.5">
              <div className="flex items-start gap-2">
                <textarea
                  aria-label={t("content.editor.overlayItem", { n: index + 1 })}
                  value={text}
                  rows={2}
                  maxLength={OVERLAY_ITEM_MAX}
                  onChange={(event) => updateOverlay(index, event.target.value)}
                  className="min-h-16 w-full rounded-control border border-control bg-surface p-3 text-base text-primary shadow-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                />
                <Button
                  variant="ghost"
                  aria-label={t("content.editor.overlayRemove", { n: index + 1 })}
                  onClick={() => edit({ overlay: overlay.filter((_, i) => i !== index) })}
                  className="shrink-0 text-lg hover:text-danger"
                >
                  ×
                </Button>
              </div>
              {dirty.overlay ? null : (
                <FieldIssues field={`overlay_text_suggestions.${index}`} issues={issues} />
              )}
            </div>
          ))}
          {overlay.length < OVERLAY_ITEMS_MAX ? (
            <div className="pt-1">
              <Button variant="secondary" onClick={() => edit({ overlay: [...overlay, ""] })} className="shadow-xs">
                {t("content.editor.overlayAdd")}
              </Button>
            </div>
          ) : null}
        </fieldset>
      ) : (
        <div className="flex flex-col gap-1.5">
          <label htmlFor={ids.caption} className="text-sm font-semibold text-primary">
            {t("content.editor.captionLabel")}
          </label>
          <textarea
            id={ids.caption}
            aria-describedby={ids.counter}
            value={caption}
            rows={6}
            onChange={(event) => edit({ caption: event.target.value })}
            className="min-h-32 w-full rounded-control border border-control bg-surface p-3.5 text-base text-primary shadow-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          />
          <Counter id={ids.counter} count={caption.length} max={CAPTION_MAX_CHARS} />
          {dirty.caption ? null : <FieldIssues field="caption" issues={issues} />}
        </div>
      )}

      {item.validation.stale ? (
        <p className="text-sm font-medium text-attention" data-testid="stale-note">
          {t("content.editor.issues.stale")}
        </p>
      ) : null}

      <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">{t("core.optionalNotes")}</summary>
      <div className="mt-3 flex flex-col gap-4">
      <TextField
        label={t("content.editor.titleLabel")}
        value={title}
        maxLength={TITLE_MAX}
        onChange={(event) => edit({ title: event.target.value })}
      />

      <div className="flex flex-col gap-1.5">
        <label htmlFor={ids.notes} className="text-sm font-semibold text-primary">
          {t("content.editor.visualNotesLabel")}
        </label>
        <textarea
          id={ids.notes}
          value={notes}
          rows={3}
          maxLength={NOTES_MAX}
          onChange={(event) => edit({ notes: event.target.value })}
          className="min-h-20 w-full rounded-control border border-control bg-surface p-3.5 text-base text-primary shadow-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        />
      </div>

      </div></details>

      {conflict ? (
        <div role="alert" data-testid="version-conflict" className="flex items-center gap-2 rounded-panel border border-attention bg-attention-subtle p-3.5 text-sm text-attention shadow-xs">
          <AlertIcon className="text-base shrink-0" />
          <p>{t("content.editor.conflict")}</p>
        </div>
      ) : null}
      {patch.error && !(conflict && patch.error.code === "VERSION_CONFLICT") ? (
        <ErrorMessage error={patch.error} />
      ) : null}
      {validate.error ? <ErrorMessage error={validate.error} /> : null}
      {checks ? <Checks result={checks} /> : null}

      <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-border">
        <Button type="submit" disabled={busy || !anyDirty || title.trim() === ""} className="shadow-xs">
          {busy ? t("content.editor.saving") : t("content.editor.save")}
        </Button>
        <Button variant="secondary" disabled={busy || validate.isPending || anyDirty} onClick={runCheck} className="shadow-xs">
          {validate.isPending ? t("content.editor.checking") : t("content.editor.check")}
        </Button>
        {actions?.(anyDirty || busy)}
        {anyDirty ? (
          <span className="text-sm font-medium text-secondary">{t("content.editor.unsaved")}</span>
        ) : saved ? (
          <span role="status" className="inline-flex items-center gap-1.5 text-sm font-semibold text-success">
            <CheckIcon className="text-base" />
            <span>{t("content.editor.saved")}</span>
          </span>
        ) : null}
      </div>
    </form>
    <aside className={`min-w-0 min-[1200px]:sticky min-[1200px]:top-24 ${panel === "preview" ? "block" : "hidden min-[1200px]:block"}`}><PostPreview key={item.media_asset_id} item={item} caption={caption} overlay={overlay} account={account} /></aside>
    </div></div>
  );
}
