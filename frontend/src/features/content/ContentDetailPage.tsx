import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { AppError } from "@/api/errors";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
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
      <div role="status" className="rounded-lg bg-blue-50 p-3 text-sm text-blue-900 ring-1 ring-blue-300" data-testid="generation-running">
        <p className="font-medium">{t("content.generation.running")}</p>
        <p>{slow ? t("content.generation.slow") : t("content.generation.hint")}</p>
      </div>
    );
  }
  if (item.generation?.status === "failed") {
    return (
      <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-400" data-testid="generation-failed">
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
    <div className="flex flex-col gap-1">
      <div>
        <Button disabled={blocked} onClick={() => setOpen(true)}>
          {t("content.actions.schedule")}
        </Button>
      </div>
      {dirty ? <p className="text-sm text-slate-600">{t("content.actions.saveFirst")}</p> : null}
      {generating ? <p className="text-sm text-slate-600">{t("content.actions.waitGeneration")}</p> : null}
      {open ? (
        <ScheduleSheet
          item={item}
          mode="submit"
          onClose={() => setOpen(false)}
          onEditText={() => {
            setOpen(false);
            // After the sheet has closed and handed focus back to its opener.
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
    <Link to={`/w/${workspace.id}/content`} className="text-sm font-medium text-indigo-800 underline">
      {t("content.back")}
    </Link>
  );

  if (query.isPending) return <p>{t("common.loading")}</p>;
  if (query.isError) {
    return (
      <div className="flex flex-col gap-3">
        {back}
        {query.error instanceof AppError && query.error.status === 404 ? (
          <p>{t("content.notFound")}</p>
        ) : (
          <ErrorMessage error={query.error} />
        )}
      </div>
    );
  }
  const item = query.data;
  const badge = contentBadge(item, t, i18n.language, workspace.timezone);

  return (
    <div className="flex flex-col gap-4">
      <div>
        {back}
        <h1 className="mt-1 text-2xl font-semibold break-words">{item.title || t("content.card.untitled")}</h1>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span>{t(`content.type.${item.content_type}`)}</span>
          <StatusBadge status={badge.status} params={badge.params} simulated={item.is_simulated} />
        </div>
      </div>
      <GenerationNotice item={item} />
      <ContentStatusPanel item={item} />
      <FailureDetail item={item} onEdit={focusEditor} />
      {item.status === "on_hold" ? <OnHoldActions item={item} onEdit={focusEditor} /> : null}
      {item.status !== "on_hold" ? (
        <div className="flex flex-wrap items-start gap-3">
          {item.status === "draft" ? <ScheduleAction item={item} dirty={dirty} /> : null}
          <CancelAction item={item} />
        </div>
      ) : null}
      <Card id={EDITOR_ID}>
        <ContentEditor item={item} onDirtyChange={onDirtyChange} />
      </Card>
    </div>
  );
}
