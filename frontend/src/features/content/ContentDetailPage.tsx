import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { AppError } from "@/api/errors";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronLeftIcon, SpinnerIcon } from "@/components/icons";
import { StatusBadge } from "@/components/StatusBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { CancelAction } from "./CancelAction";
import { ContentEditor } from "./ContentEditor";
import { ContentStatusPanel } from "./ContentStatusPanel";
import { FailureDetail } from "./FailureDetail";
import { isGenerating, useContentItem } from "./hooks";
import { OnHoldActions } from "./OnHoldActions";
import { ScheduleSheet } from "./ScheduleSheet";
import { contentBadge } from "./status";

const SLOW_AFTER_MS = 30_000;
const EDITOR_ID = "content-editor";

/** Move to the text: the way to "edit it" from a hold, a failure or a refusal. */
function focusEditor() {
  const root = document.getElementById(EDITOR_ID);
  root?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  root?.querySelector<HTMLElement>("textarea, input:not([type=file])")?.focus();
}

/** The AI draft is prepared by a job: say so while it runs, and say what is left when it failed. */
function GenerationNotice({ item }: { item: ContentItem }) {
  const { t } = useTranslation();
  const running = isGenerating(item);
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!running) return;
    const waited = Date.now() - new Date(item.created_at).getTime();
    const timer = window.setTimeout(() => setSlow(true), Math.max(0, SLOW_AFTER_MS - waited));
    return () => window.clearTimeout(timer);
  }, [running, item.created_at]);

  if (running) {
    return (
      <div
        role="status"
        className="flex items-start gap-3 rounded-panel border border-info bg-info-subtle p-4 text-sm text-info shadow-xs"
        data-testid="generation-running"
      >
        <SpinnerIcon className="size-5 shrink-0 motion-safe:animate-spin mt-0.5" />
        <div>
          <p className="font-semibold">{t("content.generation.running")}</p>
          <p className="mt-0.5 text-secondary">{slow ? t("content.generation.slow") : t("content.generation.hint")}</p>
        </div>
      </div>
    );
  }
  if (item.generation?.status === "failed") {
    return (
      <p
        className="rounded-panel border border-attention bg-attention-subtle p-4 text-sm text-attention shadow-xs font-medium"
        data-testid="generation-failed"
      >
        {t("content.generation.failed")}
      </p>
    );
  }
  return null;
}

/** Scheduling a draft: the button, and why it may be held back for a moment. */
function ScheduleAction({ item, dirty }: { item: ContentItem; dirty: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const generating = isGenerating(item);
  const blocked = dirty || generating;
  return (
    <div className="flex flex-col gap-1.5">
      <div>
        <Button disabled={blocked} onClick={() => setOpen(true)} className="shadow-xs">
          {t("content.actions.schedule")}
        </Button>
      </div>
      {dirty ? <p className="text-xs font-medium text-secondary">{t("content.actions.saveFirst")}</p> : null}
      {generating ? <p className="text-xs font-medium text-secondary">{t("content.actions.waitGeneration")}</p> : null}
      {open ? (
        <ScheduleSheet
          item={item}
          mode="submit"
          onClose={() => setOpen(false)}
          onEditText={() => {
            setOpen(false);
            window.setTimeout(focusEditor, 0);
          }}
        />
      ) : null}
    </div>
  );
}

/** One content item: where it stands and why, what can be done next, and the editor. */
export function ContentDetailPage() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const { id = "" } = useParams();
  const query = useContentItem(workspace.id, id);
  const [dirty, setDirty] = useState(false);
  const onDirtyChange = useCallback((value: boolean) => setDirty(value), []);

  const back = (
    <Link
      to={`/w/${workspace.id}/content`}
      className="inline-flex items-center gap-1.5 text-sm font-semibold text-action hover:text-action-hover transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
    >
      <ChevronLeftIcon className="text-base" />
      <span>{t("content.back")}</span>
    </Link>
  );

  if (query.isPending) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-secondary">
        <SpinnerIcon className="motion-safe:animate-spin text-base text-action" />
        <p>{t("common.loading")}</p>
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="flex flex-col gap-4 max-w-4xl">
        {back}
        {query.error instanceof AppError && query.error.status === 404 ? (
          <div className="rounded-panel border border-border bg-surface p-6 text-center text-sm text-secondary shadow-xs">
            {t("content.notFound")}
          </div>
        ) : (
          <ErrorMessage error={query.error} />
        )}
      </div>
    );
  }
  const item = query.data;
  const badge = contentBadge(item, t, i18n.language, workspace.timezone);

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="border-b border-border pb-5">
        {back}
        <h1 className="mt-3 text-2xl sm:text-3xl font-heading font-bold text-primary break-words">
          {item.title || t("content.card.untitled")}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-secondary">
          <span className="font-semibold text-primary">{t(`content.type.${item.content_type}`)}</span>
          <span className="text-secondary/40">·</span>
          <StatusBadge status={badge.status} params={badge.params} simulated={item.is_simulated} />
        </div>
      </div>

      <GenerationNotice item={item} />
      <div className="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <Card id={EDITOR_ID} className="min-w-0 p-4 sm:p-6">
        <ContentEditor item={item} onDirtyChange={onDirtyChange} />
      </Card>
      <aside className="order-first flex min-w-0 flex-col gap-4 xl:order-last xl:sticky xl:top-24">
      <ContentStatusPanel item={item} />
      <FailureDetail item={item} onEdit={focusEditor} />
      {item.status === "on_hold" ? <OnHoldActions item={item} onEdit={focusEditor} /> : null}
      {item.status !== "on_hold" ? (
        <div className="flex flex-wrap items-start gap-3">
          {item.status === "draft" ? <ScheduleAction item={item} dirty={dirty} /> : null}
          <CancelAction item={item} />
        </div>
      ) : null}
      </aside>
      </div>
    </div>
  );
}
