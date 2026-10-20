import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentIssue, ContentItem, ContentValidation } from "@/api/types";
import { AlertIcon } from "@/components/icons";
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
    <div className="flex flex-col gap-1.5" data-testid="field-issues">
      {blocking.map((issue, index) => (
        <p
          key={`${issue.code}-${index}`}
          data-testid="blocking-issue"
          data-code={issue.code}
          className="flex items-start gap-2 rounded-lg bg-red-50 p-2 text-sm text-red-900 ring-1 ring-red-300"
        >
          <AlertIcon className="mt-0.5 shrink-0" />
          <span>{blockingIssueMessage(issue, t)}</span>
        </p>
      ))}
      {blocking.length > 0 ? (
        <p className="text-xs text-slate-600">{t("content.editor.issues.blockingHint")}</p>
      ) : null}
      {grounded.map((issue, index) => {
        const fact = facts.data?.find((candidate) => candidate.key === issue.fact_key);
        return (
          <p
            key={`${issue.code}-${index}`}
            data-testid="grounded-issue"
            className="flex flex-wrap items-center gap-2 text-sm text-slate-700"
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
    <span
      id={id}
      data-testid="caption-counter"
      className={`text-sm ${over ? "font-medium text-red-700" : "text-slate-600"}`}
    >
      {over ? t("content.editor.counterOver", { count, max }) : t("content.editor.counter", { count, max })}
    </span>
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
      <p role="status" className="text-sm text-green-800" data-testid="check-clean">
        {t("content.editor.checkClean")}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2" data-testid="checks">
      {errors.length > 0 ? (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300">
          <p className="font-medium">{t("content.editor.checks.errorsLabel")}</p>
          <ul className="list-disc pl-5">
            {errors.map((item, index) => (
              <li key={`${item.code}-${index}`} data-code={item.code}>
                {checkMessage(item, t)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {warnings.length > 0 ? (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-medium">{t("content.editor.checks.warningsLabel")}</p>
          <ul className="list-disc pl-5">
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
    <div className="flex flex-col gap-3" data-testid="content-readonly">
      <p className="text-sm text-slate-600">{t("content.editor.readOnly")}</p>
      {item.content_type === "feed_image" && item.caption ? (
        <p className="break-words whitespace-pre-wrap">{item.caption}</p>
      ) : null}
      {item.content_type === "story_image" && item.overlay_text_suggestions.length > 0 ? (
        <ul className="list-disc pl-5">
          {item.overlay_text_suggestions.map((text, index) => (
            <li key={index} className="break-words whitespace-pre-wrap">
              {text}
            </li>
          ))}
        </ul>
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
}: {
  item: ContentItem;
  /** Told whenever there are unsaved changes (the page holds back "schedule" until they are saved). */
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const ids = { caption: useId(), counter: useId(), notes: useId() };
  const patch = usePatchContent(workspace.id, item.id);
  const validate = useValidateContent(workspace.id, item.id);
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
  useEffect(() => {
    onDirtyChange?.(anyDirty);
  }, [anyDirty, onDirtyChange]);

  if (!isEditable(item.status)) {
    return <ReadOnlyText item={item} />;
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
    <form
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (anyDirty && title.trim() !== "") save();
      }}
    >
      {editVoidsApproval(item.status) ? (
        <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900" data-testid="voids-approval">
          {t("content.editor.editVoidsApproval")}
        </p>
      ) : null}

      <TextField
        label={t("content.editor.titleLabel")}
        value={title}
        maxLength={TITLE_MAX}
        onChange={(event) => edit({ title: event.target.value })}
      />

      <MediaUpload
        workspaceId={workspace.id}
        contentType={item.content_type}
        mediaId={item.media_asset_id}
        onUploaded={(asset) => attachMedia(asset.id)}
        warnings={mediaWarnings}
        disabled={busy}
      />

      {isStory ? (
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium text-slate-800">{t("content.editor.overlayLabel")}</legend>
          <p className="text-sm text-slate-600" data-testid="overlay-note">
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
                  className="min-h-16 w-full rounded-lg border border-slate-300 p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
                />
                <Button
                  variant="ghost"
                  aria-label={t("content.editor.overlayRemove", { n: index + 1 })}
                  onClick={() => edit({ overlay: overlay.filter((_, i) => i !== index) })}
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
            <div>
              <Button variant="secondary" onClick={() => edit({ overlay: [...overlay, ""] })}>
                {t("content.editor.overlayAdd")}
              </Button>
            </div>
          ) : null}
        </fieldset>
      ) : (
        <div className="flex flex-col gap-1.5">
          <label htmlFor={ids.caption} className="text-sm font-medium text-slate-800">
            {t("content.editor.captionLabel")}
          </label>
          <textarea
            id={ids.caption}
            aria-describedby={ids.counter}
            value={caption}
            rows={6}
            onChange={(event) => edit({ caption: event.target.value })}
            className="min-h-32 w-full rounded-lg border border-slate-300 p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
          />
          <Counter id={ids.counter} count={caption.length} max={CAPTION_MAX_CHARS} />
          {dirty.caption ? null : <FieldIssues field="caption" issues={issues} />}
        </div>
      )}

      {item.validation.stale ? (
        <p className="text-sm text-amber-900" data-testid="stale-note">
          {t("content.editor.issues.stale")}
        </p>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <label htmlFor={ids.notes} className="text-sm font-medium text-slate-800">
          {t("content.editor.visualNotesLabel")}
        </label>
        <textarea
          id={ids.notes}
          value={notes}
          rows={3}
          maxLength={NOTES_MAX}
          onChange={(event) => edit({ notes: event.target.value })}
          className="min-h-20 w-full rounded-lg border border-slate-300 p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
        />
      </div>

      {conflict ? (
        <p role="alert" data-testid="version-conflict" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-400">
          {t("content.editor.conflict")}
        </p>
      ) : null}
      {patch.error && !(conflict && patch.error.code === "VERSION_CONFLICT") ? (
        <ErrorMessage error={patch.error} />
      ) : null}
      {validate.error ? <ErrorMessage error={validate.error} /> : null}
      {checks ? <Checks result={checks} /> : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={busy || !anyDirty || title.trim() === ""}>
          {busy ? t("content.editor.saving") : t("content.editor.save")}
        </Button>
        <Button variant="secondary" disabled={busy || validate.isPending || anyDirty} onClick={runCheck}>
          {validate.isPending ? t("content.editor.checking") : t("content.editor.check")}
        </Button>
        {anyDirty ? (
          <span className="text-sm text-slate-600">{t("content.editor.unsaved")}</span>
        ) : saved ? (
          <span role="status" className="text-sm text-green-800">
            {t("content.editor.saved")}
          </span>
        ) : null}
      </div>
    </form>
  );
}
