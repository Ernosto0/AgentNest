import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { ContentType } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { AlertIcon, CheckIcon, PlusIcon, SparkIcon, SpinnerIcon } from "@/components/icons";
import { TextField } from "@/components/TextField";
import { newRequestId } from "@/features/commands/hooks";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useContentItem, useCreateContent, useGenerateContent } from "./hooks";
import { NOTES_MAX, OBJECTIVE_MAX, TITLE_MAX } from "./limits";

export type NewContentMode = "ai" | "blank";

/** Where the AI draft stands, in the sheet that asked for it. A failure leaves a manual draft. */
function GenerationProgress({ contentId, onOpen }: { contentId: string; onOpen: () => void }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const item = useContentItem(workspace.id, contentId).data;
  const status = item?.generation?.status ?? "queued";
  const code = item?.generation?.error_code ?? null;
  const cause = code ? t(`errors.${code}.what`, { defaultValue: "" }) : "";

  return (
    <div className="flex flex-col gap-3.5 pt-1" data-testid="generation-progress" data-generation={status}>
      {status === "failed" ? (
        <div role="alert" className="flex items-start gap-3 rounded-panel bg-attention-subtle p-4 text-sm text-attention border border-attention shadow-xs">
          <AlertIcon className="text-base shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <p className="font-semibold">{t("content.generate.failedTitle")}</p>
            {cause ? <p>{cause}</p> : null}
            <p className="opacity-90">{t("content.generate.failedHint")}</p>
          </div>
        </div>
      ) : status === "succeeded" ? (
        <div role="status" className="flex items-center gap-2 rounded-panel bg-success-subtle p-4 text-sm font-semibold text-success border border-success/30 shadow-xs">
          <CheckIcon className="text-base shrink-0" />
          <p>{t("content.generate.ready")}</p>
        </div>
      ) : (
        <div role="status" className="flex items-start gap-3 rounded-panel bg-info-subtle p-4 text-sm text-info border border-info shadow-xs">
          <SpinnerIcon className="motion-safe:animate-spin text-lg shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <p className="font-semibold">{t("content.generate.running")}</p>
            <p className="text-secondary">{t("content.generate.runningHint")}</p>
          </div>
        </div>
      )}
      <div className="pt-1">
        <Button onClick={onOpen} className="shadow-xs">{t("content.generate.open")}</Button>
      </div>
    </div>
  );
}

/**
 * Start a piece of content: ask the assistant for a draft, or begin with a blank one and write it
 * yourself. Both are drafts (nothing is published): the AI is never the only way in, and an AI
 * failure simply leaves the manual draft behind.
 */
export function GenerateSheet({
  initialMode,
  initialType,
  initialObjective = "",
  onClose,
}: {
  initialMode: NewContentMode;
  initialType?: ContentType;
  /** A brief typed elsewhere (the content composer): the sheet opens with it, to review and send. */
  initialObjective?: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const navigate = useNavigate();
  const ids = { objective: useId(), notes: useId() };
  const accounts = useSocialAccounts(workspace.id);
  const generate = useGenerateContent(workspace.id);
  const create = useCreateContent(workspace.id);
  // One id per sheet: a resubmission of the same blank draft returns the first one.
  const [blankRequestId] = useState(newRequestId);

  const [mode, setMode] = useState<NewContentMode>(initialMode);
  const [type, setType] = useState<ContentType>(initialType ?? "feed_image");
  const [objective, setObjective] = useState(initialObjective.slice(0, OBJECTIVE_MAX));
  const [notes, setNotes] = useState("");
  const [title, setTitle] = useState("");
  const [createdId, setCreatedId] = useState<string | null>(null);

  const account = accounts.data?.find((candidate) => candidate.status !== "disconnected") ?? null;
  const open = (id: string) => {
    onClose();
    navigate(`/w/${workspace.id}/content/${id}`);
  };
  const busy = generate.isPending || create.isPending;

  const submitAi = () => {
    generate.mutate(
      { content_type: type, objective: objective.trim(), notes: notes.trim() === "" ? null : notes.trim() },
      { onSuccess: (item) => setCreatedId(item.id) },
    );
  };
  const submitBlank = () => {
    create.mutate(
      { content_type: type, title: title.trim(), client_request_id: blankRequestId },
      { onSuccess: (item) => open(item.id) },
    );
  };

  const typeChoice = (
    <fieldset className="flex flex-col gap-2.5" disabled={createdId !== null}>
      <legend className="text-sm font-semibold text-primary">{t("content.generate.typeLabel")}</legend>
      <div className="flex flex-wrap gap-4">
        {(["feed_image", "story_image"] as const).map((option) => (
          <label key={option} className="flex min-h-11 items-center gap-2.5 cursor-pointer text-sm font-medium text-primary">
            <input
              type="radio"
              name="content-type"
              checked={type === option}
              onChange={() => setType(option)}
              className="size-4 accent-action focus-visible:outline-2 focus-visible:outline-focus"
            />
            <span>{t(`content.type.${option}`)}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );

  return (
    <BottomSheet title={t("content.generate.title")} onClose={onClose}>
      <div className="flex flex-col gap-5" data-testid="generate-sheet">
        {/* Mode Selector Tabs */}
        <div
          role="tablist"
          aria-label={t("content.generate.modeLabel")}
          className="inline-flex rounded-control bg-surface-subtle p-1 border border-border shadow-xs"
        >
          {(["ai", "blank"] as const).map((option) => (
            <button
              key={option}
              role="tab"
              type="button"
              aria-selected={mode === option}
              disabled={createdId !== null}
              onClick={() => setMode(option)}
              className={`inline-flex items-center gap-1.5 min-h-10 rounded-control px-4 text-sm font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60 ${
                mode === option
                  ? "bg-action text-on-action shadow-xs"
                  : "text-secondary hover:text-primary hover:bg-surface/50"
              }`}
            >
              {option === "ai" ? (
                <>
                  <SparkIcon className="text-base" />
                  <span>{t("content.generate.modeAi")}</span>
                </>
              ) : (
                <>
                  <PlusIcon className="text-base" />
                  <span>{t("content.generate.modeBlank")}</span>
                </>
              )}
            </button>
          ))}
        </div>

        {typeChoice}

        {mode === "ai" ? (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (objective.trim() !== "" && !busy && createdId === null) submitAi();
            }}
          >
            <div className="flex flex-col gap-1.5">
              <label htmlFor={ids.objective} className="text-sm font-semibold text-primary">
                {t("content.generate.objectiveLabel")}
              </label>
              <textarea
                id={ids.objective}
                value={objective}
                rows={3}
                maxLength={OBJECTIVE_MAX}
                disabled={createdId !== null}
                onChange={(event) => setObjective(event.target.value)}
                className="min-h-24 w-full rounded-control border border-control bg-surface p-3.5 text-base text-primary shadow-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:bg-surface-subtle"
              />
              <p className="text-xs text-secondary">{t("content.generate.objectiveHint")}</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={ids.notes} className="text-sm font-semibold text-primary">
                {t("content.generate.notesLabel")}
              </label>
              <textarea
                id={ids.notes}
                value={notes}
                rows={2}
                maxLength={NOTES_MAX}
                disabled={createdId !== null}
                onChange={(event) => setNotes(event.target.value)}
                className="min-h-16 w-full rounded-control border border-control bg-surface p-3.5 text-base text-primary shadow-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:bg-surface-subtle"
              />
            </div>
            <div className="rounded-panel border border-border bg-surface-subtle p-3.5 text-sm" data-testid="generate-account">
              <p className="font-semibold text-primary">{t("content.generate.accountLabel")}</p>
              {account ? (
                <p className="mt-1 inline-flex flex-wrap items-center gap-2 font-medium text-primary">
                  <span>@{account.username ?? account.id}</span>
                  {account.is_simulated ? <SimulatedBadge /> : null}
                </p>
              ) : (
                <p className="mt-1 text-secondary">{t("content.generate.accountNone")}</p>
              )}
              {account ? <p className="mt-1 text-xs text-secondary">{t("content.generate.accountHint")}</p> : null}
            </div>
            {generate.error ? <ErrorMessage error={generate.error} /> : null}
            {createdId === null ? (
              <div className="pt-2">
                <Button type="submit" disabled={busy || objective.trim() === ""} className="shadow-xs">
                  {generate.isPending ? t("content.generate.submitting") : t("content.generate.submit")}
                </Button>
              </div>
            ) : (
              <GenerationProgress contentId={createdId} onOpen={() => open(createdId)} />
            )}
          </form>
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (title.trim() !== "" && !busy) submitBlank();
            }}
          >
            <TextField
              label={t("content.generate.titleLabel")}
              value={title}
              maxLength={TITLE_MAX}
              onChange={(event) => setTitle(event.target.value)}
            />
            <p className="-mt-2 text-xs text-secondary">{t("content.generate.titleHint")}</p>
            {create.error ? <ErrorMessage error={create.error} /> : null}
            <div className="pt-2">
              <Button type="submit" disabled={busy || title.trim() === ""} className="shadow-xs">
                {create.isPending ? t("content.generate.submitting") : t("content.generate.blankSubmit")}
              </Button>
            </div>
          </form>
        )}
      </div>
    </BottomSheet>
  );
}
