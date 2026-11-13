import { useRef, useState, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice, Skeleton } from "@/components/Feedback";
import { HourglassIcon, TrashIcon } from "@/components/icons";
import { TextField } from "@/components/TextField";
import { absoluteTime } from "@/features/agent/presentation";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useCancelWorkspaceDeletion, useRequestWorkspaceDeletion, useWorkspaceDeletionStatus } from "./hooks";
import { FOCUS, PanelTitle, SettingsPanel } from "./SettingsParts";

/**
 * Owner-only workspace deletion (data-rights router, ADR-025 §3.3). The server owns every rule:
 * the request pauses automation, disconnects accounts and cancels pending work at once; the
 * owner can cancel until `deletion_scheduled_at`; cancelling restores the workspace status only.
 */
export function WorkspaceDangerZone() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const status = useWorkspaceDeletionStatus(workspace.id);
  const request = useRequestWorkspaceDeletion(workspace.id);
  const cancel = useCancelWorkspaceDeletion(workspace.id);
  const [dialog, setDialog] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);

  const deletion = status.data;
  const base = `/w/${workspace.id}`;

  let body;
  if (status.isPending) {
    body = (
      <div className="px-4 pb-4 sm:px-5 sm:pb-5">
        <Skeleton label={t("common.loading")} rows={2} />
      </div>
    );
  } else if (status.isError) {
    body = (
      <div className="px-4 pb-4 sm:px-5 sm:pb-5">
        <ErrorMessage error={status.error} />
      </div>
    );
  } else if (deletion?.is_deleting) {
    const date = deletion.deletion_scheduled_at ? absoluteTime(deletion.deletion_scheduled_at, i18n.language, workspace.timezone) : null;
    const days = deletion.days_remaining ?? 0;
    body = (
      <div className="flex min-w-0 flex-col gap-3 border-t border-attention/30 px-4 py-4 sm:px-5 sm:pb-5">
        <p className="text-body text-primary">
          {date ? t("settings.danger.scheduledBody", { name: workspace.name, date }) : t("settings.danger.scheduledNoDate", { name: workspace.name })}
        </p>
        <p className="text-metadata text-secondary">{t("settings.danger.scheduledPaused")}</p>
        {deletion.can_cancel ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Button variant="secondary" pending={cancel.isPending} onClick={() => cancel.mutate(undefined, { onSuccess: () => setCancelled(true) })}>
              {t("settings.danger.cancel")}
            </Button>
            <span className="text-metadata font-medium text-attention">
              {days > 0 ? t("settings.danger.daysLeft", { count: days }) : t("settings.danger.lastDay")}
            </span>
          </div>
        ) : (
          <p className="text-metadata font-medium text-attention">{t("settings.danger.tooLate")}</p>
        )}
        {cancel.isError ? <ErrorMessage error={cancel.error} /> : null}
      </div>
    );
  } else {
    body = (
      <div className="flex min-w-0 flex-col gap-3 px-4 pb-4 sm:px-5 sm:pb-5">
        {cancelled ? (
          <Notice tone="success" title={t("settings.danger.cancelledTitle")} live="polite">
            <p>{t("settings.danger.cancelledBody")}</p>
            <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
              <Link to={`${base}/more/settings/connections`} className={`font-semibold underline underline-offset-2 ${FOCUS}`}>
                {t("settings.danger.reconnect")}
              </Link>
              <Link to={`${base}/more/automation`} className={`font-semibold underline underline-offset-2 ${FOCUS}`}>
                {t("settings.danger.automation")}
              </Link>
            </p>
          </Notice>
        ) : null}
        <p className="max-w-prose text-metadata text-secondary">{t("settings.danger.summary")}</p>
      </div>
    );
  }

  const deleting = Boolean(deletion?.is_deleting);
  return (
    <SettingsPanel
      as="section"
      id="danger-zone"
      tone={deleting ? "attention" : "danger"}
      aria-labelledby="settings-danger-title"
      className="scroll-mt-6 md:scroll-mt-24"
    >
      <PanelTitle
        id="settings-danger-title"
        icon={deleting ? <HourglassIcon /> : <TrashIcon />}
        iconTone={deleting ? "neutral" : "danger"}
        title={deleting ? t("settings.danger.scheduledTitle") : t("settings.danger.title")}
        description={deleting ? undefined : t("settings.danger.description", { name: workspace.name })}
        action={
          !deleting && status.isSuccess ? (
            <Button
              ref={opener}
              variant="secondary"
              className="border-danger/40 text-danger enabled:hover:bg-danger-subtle sm:min-h-10"
              onClick={() => {
                request.reset();
                setCancelled(false);
                setDialog(true);
              }}
            >
              {t("settings.danger.open")}
            </Button>
          ) : undefined
        }
      />
      {body}
      {dialog ? (
        <DeleteDialog
          name={workspace.name}
          pending={request.isPending}
          error={request.error}
          onClose={() => setDialog(false)}
          onConfirm={() => request.mutate(undefined, { onSuccess: () => setDialog(false) })}
          returnFocusRef={opener}
        />
      ) : null}
    </SettingsPanel>
  );
}

function DeleteDialog({
  name,
  pending,
  error,
  onClose,
  onConfirm,
  returnFocusRef,
}: {
  name: string;
  pending: boolean;
  error: unknown;
  onClose: () => void;
  onConfirm: () => void;
  returnFocusRef: RefObject<HTMLButtonElement | null>;
}) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState("");
  const input = useRef<HTMLInputElement>(null);
  // Exact (trimmed) match: deliberate typing, never a guess at case or spelling.
  const matches = typed.trim() === name.trim();
  const steps = [
    ["now", t("settings.danger.stepNowTitle"), t("settings.danger.stepNow")],
    ["grace", t("settings.danger.stepGraceTitle"), t("settings.danger.stepGrace")],
    ["after", t("settings.danger.stepAfterTitle"), t("settings.danger.stepAfter")],
  ] as const;

  return (
    <BottomSheet
      title={t("settings.danger.dialogTitle", { name })}
      onClose={() => {
        if (!pending) onClose();
      }}
      dismissible={!pending}
      initialFocusRef={input}
      returnFocusRef={returnFocusRef}
      footer={
        <div className="flex flex-wrap gap-2">
          <Button variant="danger" pending={pending} disabled={!matches} onClick={onConfirm}>
            {t("settings.danger.confirm")}
          </Button>
          <Button variant="secondary" disabled={pending} onClick={onClose}>
            {t("common.cancel")}
          </Button>
        </div>
      }
    >
      <form
        className="flex min-w-0 flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (matches && !pending) onConfirm();
        }}
      >
        <ol className="flex flex-col gap-3">
          {steps.map(([key, title, text], index) => (
            <li key={key} className="flex gap-3">
              <span
                aria-hidden="true"
                className="flex size-6 shrink-0 items-center justify-center rounded-full bg-danger-subtle text-xs font-bold text-danger"
              >
                {index + 1}
              </span>
              <div className="min-w-0">
                <p className="text-body font-semibold text-primary">{title}</p>
                <p className="text-metadata text-secondary">{text}</p>
              </div>
            </li>
          ))}
        </ol>
        <TextField
          ref={input}
          label={t("settings.danger.typeName", { name })}
          value={typed}
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="off"
          onChange={(event) => setTyped(event.target.value)}
        />
        {error ? <ErrorMessage error={error} /> : null}
      </form>
    </BottomSheet>
  );
}
