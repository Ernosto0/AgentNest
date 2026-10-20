import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { ContentType } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { SpinnerIcon } from "@/components/icons";
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
    <div className="flex flex-col gap-3" data-testid="generation-progress" data-generation={status}>
      {status === "failed" ? (
        <div role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-400">
          <p className="font-medium">{t("content.generate.failedTitle")}</p>
          {cause ? <p>{cause}</p> : null}
          <p>{t("content.generate.failedHint")}</p>
        </div>
      ) : status === "succeeded" ? (
        <p role="status" className="font-medium text-green-800">
          {t("content.generate.ready")}
        </p>
      ) : (
        <div role="status" className="rounded-lg bg-blue-50 p-3 text-sm text-blue-900 ring-1 ring-blue-300">
          <p className="inline-flex items-center gap-2 font-medium">
            <SpinnerIcon className="animate-spin text-xl" />
            {t("content.generate.running")}
          </p>
          <p>{t("content.generate.runningHint")}</p>
        </div>
      )}
      <div>
        <Button onClick={onOpen}>{t("content.generate.open")}</Button>
      </div>
    </div>
  );
}

/**
 * Start a piece of content: ask the assistant for a draft, or begin with a blank one and write it
 * yourself. Both are drafts (nothing is published): the AI is never the only way in, and an AI
 * failure simply leaves the manual draft behind.
 */
export function GenerateSheet({ initialMode, onClose }: { initialMode: NewContentMode; onClose: () => void }) {
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
  const [type, setType] = useState<ContentType>("feed_image");
  const [objective, setObjective] = useState("");
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
    <fieldset className="flex flex-col gap-2" disabled={createdId !== null}>
      <legend className="text-sm font-medium text-slate-800">{t("content.generate.typeLabel")}</legend>
      <div className="flex flex-wrap gap-4">
        {(["feed_image", "story_image"] as const).map((option) => (
          <label key={option} className="flex min-h-11 items-center gap-2">
            <input
              type="radio"
              name="content-type"
              checked={type === option}
              onChange={() => setType(option)}
              className="size-5"
            />
            {t(`content.type.${option}`)}
          </label>
        ))}
      </div>
    </fieldset>
  );

  return (
    <BottomSheet title={t("content.generate.title")} onClose={onClose}>
      <div className="flex flex-col gap-4" data-testid="generate-sheet">
        <div role="tablist" aria-label={t("content.generate.modeLabel")} className="flex gap-2">
          {(["ai", "blank"] as const).map((option) => (
            <button
              key={option}
              role="tab"
              type="button"
              aria-selected={mode === option}
              disabled={createdId !== null}
              onClick={() => setMode(option)}
              className={`min-h-11 rounded-lg px-4 font-medium focus-visible:outline-2 focus-visible:outline-indigo-600 disabled:opacity-60 ${
                mode === option ? "bg-indigo-700 text-white" : "bg-white text-slate-800 ring-1 ring-slate-300"
              }`}
            >
              {option === "ai" ? t("content.generate.modeAi") : t("content.generate.modeBlank")}
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
              <label htmlFor={ids.objective} className="text-sm font-medium text-slate-800">
                {t("content.generate.objectiveLabel")}
              </label>
              <textarea
                id={ids.objective}
                value={objective}
                rows={3}
                maxLength={OBJECTIVE_MAX}
                disabled={createdId !== null}
                onChange={(event) => setObjective(event.target.value)}
                className="min-h-20 w-full rounded-lg border border-slate-300 p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
              />
              <p className="text-xs text-slate-600">{t("content.generate.objectiveHint")}</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={ids.notes} className="text-sm font-medium text-slate-800">
                {t("content.generate.notesLabel")}
              </label>
              <textarea
                id={ids.notes}
                value={notes}
                rows={2}
                maxLength={NOTES_MAX}
                disabled={createdId !== null}
                onChange={(event) => setNotes(event.target.value)}
                className="min-h-16 w-full rounded-lg border border-slate-300 p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
              />
            </div>
            <div className="text-sm" data-testid="generate-account">
              <p className="font-medium text-slate-800">{t("content.generate.accountLabel")}</p>
              {account ? (
                <p className="inline-flex flex-wrap items-center gap-2">
                  @{account.username ?? account.id}
                  {account.is_simulated ? <SimulatedBadge /> : null}
                </p>
              ) : (
                <p className="text-slate-700">{t("content.generate.accountNone")}</p>
              )}
              {account ? <p className="text-xs text-slate-600">{t("content.generate.accountHint")}</p> : null}
            </div>
            {generate.error ? <ErrorMessage error={generate.error} /> : null}
            {createdId === null ? (
              <div>
                <Button type="submit" disabled={busy || objective.trim() === ""}>
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
            <p className="-mt-2 text-xs text-slate-600">{t("content.generate.titleHint")}</p>
            {create.error ? <ErrorMessage error={create.error} /> : null}
            <div>
              <Button type="submit" disabled={busy || title.trim() === ""}>
                {create.isPending ? t("content.generate.submitting") : t("content.generate.blankSubmit")}
              </Button>
            </div>
          </form>
        )}
      </div>
    </BottomSheet>
  );
}
