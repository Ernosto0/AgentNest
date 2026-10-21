import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AppError } from "@/api/errors";
import type { ContentCheckItem, ContentIssue, ContentItem } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ContentPreview } from "./ContentPreview";
import { useReapproveContent, useSubmitContent, type ScheduleInput } from "./hooks";
import { SCHEDULE_ITEM_CODES, checkMessage, timezoneLabel } from "./messages";
import {
  APPROVAL_LEAD_MINUTES,
  defaultSchedule,
  localToInstant,
  scheduleProblem,
  toLocalFields,
} from "./schedule";

type When = "later" | "now";

const SUMMARY_LABELS = {
  media: "content.schedule.summaryMedia",
  caption: "content.schedule.summaryCaption",
  overlay: "content.schedule.summaryOverlay",
  overlayNote: "content.schedule.overlayNote",
  noMedia: "content.schedule.noMedia",
  noCaption: "content.schedule.noCaption",
};

/** The time the sheet opens on: the item's own, if it is comfortably ahead, else an hour from now. */
function initialFields(item: ContentItem, timezone: string): { date: string; time: string } {
  const now = Date.now();
  if (item.scheduled_at && new Date(item.scheduled_at).getTime() > now + (APPROVAL_LEAD_MINUTES + 5) * 60_000) {
    return toLocalFields(new Date(item.scheduled_at), timezone);
  }
  return defaultSchedule(new Date(now), timezone);
}

function asCheckItems(error: AppError): { errors: ContentCheckItem[]; warnings: ContentCheckItem[] } {
  const warnings = Array.isArray(error.params.warnings) ? (error.params.warnings as ContentCheckItem[]) : [];
  return {
    errors: error.fieldErrors.map((item) => ({ code: item.code, field: item.field, params: item.params })),
    warnings,
  };
}

/** The claim issues that block (a value that is not a verified fact), from `CLAIM_VALIDATION_FAILED`. */
function claimIssues(item: ContentCheckItem): ContentIssue[] {
  const issues = item.params?.issues;
  return Array.isArray(issues) ? (issues as ContentIssue[]).filter((issue) => !issue.matches_verified) : [];
}

/**
 * What the server refused, in plain language: every rule that failed at once (plan.md G17).
 * Time rules appear under the time fields, the rest as a list; a text problem names the value
 * (for a re-approval after a price change, that is the old price) and leads to the editor.
 */
function SubmitProblems({
  error,
  part,
  onEditText,
}: {
  error: AppError;
  part: "schedule" | "other";
  onEditText: () => void;
}) {
  const { t } = useTranslation();
  if (error.code !== "CONTENT_VALIDATION_FAILED") {
    return part === "other" ? <ErrorMessage error={error} /> : null;
  }
  const { errors, warnings } = asCheckItems(error);
  // A refusal that lists nothing still says that the item cannot be submitted yet.
  if (errors.length === 0) return part === "other" ? <ErrorMessage error={error} /> : null;
  const mine = errors.filter((item) => SCHEDULE_ITEM_CODES.includes(item.code) === (part === "schedule"));
  if (mine.length === 0 && (part === "schedule" || warnings.length === 0)) return null;

  if (part === "schedule") {
    return (
      <ul role="alert" data-testid="schedule-errors" className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300">
        {mine.map((item, index) => (
          <li key={`${item.code}-${index}`} data-code={item.code}>
            {checkMessage(item, t)}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className="flex flex-col gap-2" data-testid="submit-problems">
      {mine.length > 0 ? (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300">
          <p className="font-medium">{t("content.schedule.problemsTitle")}</p>
          <ul className="mt-1 list-disc pl-5">
            {mine.map((item, index) => (
              <li key={`${item.code}-${index}`} data-code={item.code}>
                {checkMessage(item, t)}
                {claimIssues(item).length > 0 ? (
                  <ul className="list-disc pl-5">
                    {claimIssues(item).map((issue, position) => (
                      <li key={position} data-testid="claim-issue">
                        {t("content.schedule.claimIssue", { text: issue.text })}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
          {mine.some((item) => item.code === "CLAIM_VALIDATION_FAILED") ? (
            <Button variant="secondary" className="mt-2" onClick={onEditText}>
              {t("content.schedule.editText")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {warnings.length > 0 ? (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900" data-testid="submit-warnings">
          <p className="font-medium">{t("content.schedule.warningsTitle")}</p>
          <ul className="mt-1 list-disc pl-5">
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

interface ScheduleSheetProps {
  item: ContentItem;
  /** `reapprove` approves a held item again, as it is; `submit` sends a draft. */
  mode: "submit" | "reapprove";
  onClose: () => void;
  /** Leave the sheet and go to the text (a problem with the words needs the editor). */
  onEditText: () => void;
}

/**
 * Pick when it goes out and see exactly what will be posted. Staff can only ask for approval
 * (they never see "publish now": nobody without `content.approve` can publish immediately);
 * an owner or manager approves and schedules in one step. The time is the wall-clock time in the
 * workspace timezone, which the server converts (INV-19).
 */
export function ScheduleSheet({ item, mode, onClose, onEditText }: ScheduleSheetProps) {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canApprove = role === "owner" || role === "manager";
  const accounts = useSocialAccounts(workspace.id);
  const submit = useSubmitContent(workspace.id, item.id);
  const reapprove = useReapproveContent(workspace.id, item.id);
  const action = mode === "reapprove" ? reapprove : submit;

  const [when, setWhen] = useState<When>("later");
  const [fields, setFields] = useState(() => initialFields(item, workspace.timezone));
  const zone = timezoneLabel(workspace.timezone, t);
  const account = accounts.data?.find((candidate) => candidate.status !== "disconnected") ?? null;

  const filled = fields.date !== "" && fields.time !== "";
  const problem =
    when === "later" && filled
      ? scheduleProblem(fields.date, fields.time, workspace.timezone, new Date(), !canApprove)
      : null;
  const instant = when === "later" && filled ? localToInstant(fields.date, fields.time, workspace.timezone) : null;
  const whenText =
    when === "now"
      ? t("content.schedule.whenNow")
      : t("content.schedule.whenAt", {
          zone,
          when: instant
            ? instant.toLocaleString(i18n.language, {
                dateStyle: "long",
                timeStyle: "short",
                timeZone: workspace.timezone,
              })
            : `${fields.date} ${fields.time}`,
        });

  const send = () => {
    const schedule: ScheduleInput = when === "now" ? "now" : { local_date: fields.date, local_time: fields.time };
    if (mode === "reapprove") {
      reapprove.mutate({ schedule, expectedVersion: item.version }, { onSuccess: onClose });
    } else {
      submit.mutate({ schedule, selfApprove: canApprove, expectedVersion: item.version }, { onSuccess: onClose });
    }
  };

  const label = !canApprove
    ? t("content.schedule.submitStaff")
    : mode === "reapprove"
      ? when === "now"
        ? t("content.schedule.submitReapproveNow")
        : t("content.schedule.submitReapprove")
      : when === "now"
        ? t("content.schedule.submitNow")
        : t("content.schedule.submitApprove");

  const note = !canApprove
    ? t("content.schedule.staffNote")
    : when === "now"
      ? t("content.schedule.nowNote")
      : t("content.schedule.approverNote");

  const canSend = !action.isPending && problem === null && (when === "now" || filled);
  const error = action.error;

  return (
    <BottomSheet
      title={mode === "reapprove" ? t("content.schedule.reapproveTitle") : t("content.schedule.title")}
      onClose={onClose}
      footer={
        <div className="flex flex-wrap gap-2">
          <Button disabled={!canSend} onClick={send}>
            {action.isPending ? t("content.schedule.submitting") : label}
          </Button>
          <Button variant="secondary" disabled={action.isPending} onClick={onClose}>
            {t("common.cancel")}
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4" data-testid="schedule-sheet">
        {canApprove ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium text-slate-800">{t("content.schedule.whenLabel")}</legend>
            {(["later", "now"] as const).map((option) => (
              <label key={option} className="flex min-h-11 items-center gap-3">
                <input
                  type="radio"
                  name="schedule-when"
                  value={option}
                  checked={when === option}
                  onChange={() => setWhen(option)}
                  className="size-5"
                />
                <span>{option === "now" ? t("content.schedule.optNow") : t("content.schedule.optLater")}</span>
              </label>
            ))}
          </fieldset>
        ) : null}

        {when === "later" ? (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
                {t("content.schedule.dateLabel")}
                <input
                  type="date"
                  value={fields.date}
                  onChange={(event) => setFields((current) => ({ ...current, date: event.target.value }))}
                  className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base font-normal focus-visible:outline-2 focus-visible:outline-indigo-600"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
                {t("content.schedule.timeLabel")}
                <input
                  type="time"
                  value={fields.time}
                  onChange={(event) => setFields((current) => ({ ...current, time: event.target.value }))}
                  className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base font-normal focus-visible:outline-2 focus-visible:outline-indigo-600"
                />
              </label>
            </div>
            <p className="text-sm font-medium text-slate-800" data-testid="timezone-label">
              {zone}
            </p>
            <p className="text-xs text-slate-600">{t("content.schedule.timezoneHint", { zone })}</p>
            {problem ? (
              <p
                role="status"
                data-testid="schedule-precheck"
                data-code={problem}
                className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300"
              >
                {checkMessage(
                  {
                    code: problem,
                    params:
                      problem === "SCHEDULE_TOO_SOON_FOR_APPROVAL"
                        ? { minutes: APPROVAL_LEAD_MINUTES }
                        : problem === "SCHEDULE_TIME_NONEXISTENT"
                          ? { local_date: fields.date, local_time: fields.time, timezone: workspace.timezone }
                          : {},
                  },
                  t,
                )}
              </p>
            ) : null}
            {error ? <SubmitProblems error={error} part="schedule" onEditText={onEditText} /> : null}
          </div>
        ) : null}

        <section aria-label={t("content.schedule.summaryTitle")} data-testid="schedule-summary" className="flex flex-col gap-2 rounded-xl bg-slate-50 p-3">
          <h3 className="font-medium">{t("content.schedule.summaryTitle")}</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="text-slate-600">{t("content.schedule.summaryType")}</dt>
            <dd>{t(`content.type.${item.content_type}`)}</dd>
            <dt className="text-slate-600">{t("content.schedule.summaryAccount")}</dt>
            <dd data-testid="summary-account">
              {account ? (
                <span className="inline-flex flex-wrap items-center gap-2">
                  @{account.username ?? account.id}
                  {account.is_simulated ? <SimulatedBadge /> : null}
                </span>
              ) : (
                t("content.schedule.noAccount")
              )}
            </dd>
            <dt className="text-slate-600">{t("content.schedule.summaryWhen")}</dt>
            <dd data-testid="summary-when">{whenText}</dd>
          </dl>
          <ContentPreview
            contentType={item.content_type}
            caption={item.caption}
            overlay={item.overlay_text_suggestions}
            mediaId={item.media_asset_id}
            mediaDeleted={item.media_deleted}
            labels={SUMMARY_LABELS}
          />
        </section>

        <p className="text-sm text-slate-700">{note}</p>
        {mode === "reapprove" ? <p className="text-sm text-slate-700">{t("content.schedule.reapproveNote")}</p> : null}

        {error ? <SubmitProblems error={error} part="other" onEditText={onEditText} /> : null}
      </div>
    </BottomSheet>
  );
}
