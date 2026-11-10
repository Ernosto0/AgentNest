import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ReplyDraft } from "@/api/types";
import { ClockIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useWindowMinutes } from "./hooks";

/** What a chip needs: the text, and where it comes from. A value found by matching (not rendered) has no version. */
export interface ChipFact {
  display: string;
  label: string;
  version?: number | null;
}

/** A value taken from a verified fact. Tapping it shows where it comes from. */
export function FactChip({ fact }: { fact: ChipFact }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        type="button"
        data-testid="fact-chip"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="rounded-control bg-success-subtle px-1.5 py-0.5 font-semibold text-success border border-success/40 transition-colors hover:bg-success-subtle/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        {fact.display}
      </button>
      {open ? (
        <span
          role="status"
          className="absolute top-full left-0 z-20 mt-1.5 w-60 rounded-control bg-navigation p-2.5 text-metadata font-normal text-navigation-text shadow-sm border border-navigation-selected/20"
        >
          {fact.version == null
            ? t("convo.draft.sourceUnversioned", { label: fact.label })
            : t("convo.draft.source", { label: fact.label, version: fact.version })}
        </span>
      ) : null}
    </span>
  );
}

/** The draft text with each value drawn as a fact chip (spans from the server). */
export function DraftText({ draft }: { draft: ReplyDraft }) {
  const text = draft.text ?? "";
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  [...draft.rendered_facts]
    .sort((a, b) => (a.span[0] ?? 0) - (b.span[0] ?? 0))
    .forEach((fact, index) => {
      const start = fact.span[0] ?? 0;
      const end = fact.span[1] ?? 0;
      if (start < cursor || end > text.length) return;
      parts.push(text.slice(cursor, start));
      parts.push(<FactChip key={`${fact.fact_id}-${index}`} fact={fact} />);
      cursor = end;
    });
  parts.push(text.slice(cursor));
  return (
    <p className="break-words whitespace-pre-wrap text-form text-primary leading-relaxed" data-testid="draft-text">
      {parts}
    </p>
  );
}

/** Why the assistant decided this way: one chip per reason code. */
export function ReasonChips({ reasons }: { reasons: string[] }) {
  const { t, i18n } = useTranslation();
  if (reasons.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label={t("convo.draft.reasons")}>
      {reasons.map((code) => (
        <li
          key={code}
          className="inline-flex items-center rounded-full border border-action/10 bg-surface/80 px-2.5 py-0.5 text-xs leading-5 font-medium text-secondary"
        >
          {i18n.exists(`convo.reason.${code}`) ? t(`convo.reason.${code}`) : code}
        </li>
      ))}
    </ul>
  );
}

/**
 * Time left to answer (Instagram allows 24 hours after the customer's last message).
 * `compact` suits list rows: a short visible label with the full sentence for screen readers.
 */
export function WindowTimer({ endsAt, compact = false }: { endsAt: string | null; compact?: boolean }) {
  const { t } = useTranslation();
  const minutes = useWindowMinutes(endsAt);
  if (minutes === null) return null;
  const closed = minutes <= 0;
  const full = closed
    ? t("convo.window.closed")
    : minutes >= 60
      ? t("convo.window.hours", { count: Math.floor(minutes / 60) })
      : t("convo.window.minutes", { count: minutes });
  const tone = closed ? "text-danger" : minutes < 120 ? "text-attention" : "text-secondary";
  if (!compact) {
    return (
      <span className={`inline-flex items-center gap-1.5 text-metadata font-medium ${tone}`} data-testid={closed ? undefined : "window-timer"}>
        <ClockIcon aria-hidden="true" className="shrink-0 text-sm" />
        {full}
      </span>
    );
  }
  const short = closed
    ? t("convo.window.closedShort")
    : minutes >= 60
      ? t("convo.window.hoursShort", { count: Math.floor(minutes / 60) })
      : t("convo.window.minutesShort", { count: minutes });
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs leading-4 font-medium whitespace-nowrap ${tone}`}
      data-testid={closed ? undefined : "window-timer"}
      title={full}
    >
      <ClockIcon aria-hidden="true" className="shrink-0 text-[0.8125rem]" />
      <span aria-hidden="true">{short}</span>
      <span className="sr-only">{full}</span>
    </span>
  );
}

type ApprovalState = NonNullable<ReplyDraft["approval_state"]>;

/**
 * Where the approval of a reply stands, for people who cannot decide it: who must approve and
 * by when, or who approved or rejected it, when, and their note. A reply approved by policy has
 * no person to name, so nothing is said (the reason chip already does).
 */
export function ApprovalStateNote({ state, showPending }: { state: ApprovalState; showPending: boolean }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const when = (value: string) =>
    new Date(value).toLocaleString(i18n.language, { dateStyle: "short", timeStyle: "short", timeZone: workspace.timezone });
  const name = state.decided_by_name ?? t("convo.draft.approvalState.someone");
  let line: string | null = null;
  if (state.status === "pending" && showPending) {
    line = t("convo.draft.approvalState.pending", { time: when(state.expires_at) });
  } else if (state.status === "approved" && state.decided_by_name && state.decided_at) {
    line = t("convo.draft.approvalState.approved", { name, time: when(state.decided_at) });
  } else if (state.status === "rejected" && state.decided_at) {
    line = t("convo.draft.approvalState.rejected", { name, time: when(state.decided_at) });
  } else if (state.status === "expired") {
    line = t("convo.draft.approvalState.expired", { time: when(state.expires_at) });
  }
  if (line === null) return null;
  return (
    <div
      className="rounded-xl bg-surface/70 px-3.5 py-2.5 text-body text-secondary"
      data-testid="approval-state"
      data-approval-status={state.status}
    >
      <p className="font-medium text-primary">{line}</p>
      {state.decision_note ? (
        <p className="mt-1 text-secondary">{t("convo.draft.approvalState.note", { note: state.decision_note })}</p>
      ) : null}
    </div>
  );
}
