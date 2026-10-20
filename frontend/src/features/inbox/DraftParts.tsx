import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ReplyDraft } from "@/api/types";
import { useCurrentWorkspace } from "@/features/workspaces/context";

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
        className="rounded-md bg-emerald-50 px-1.5 font-semibold text-emerald-900 ring-1 ring-emerald-600 ring-inset focus-visible:outline-2 focus-visible:outline-indigo-600"
      >
        {fact.display}
      </button>
      {open ? (
        <span
          role="status"
          className="absolute top-full left-0 z-10 mt-1 w-56 rounded-lg bg-slate-900 p-2 text-sm font-normal text-white shadow-lg"
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
    <p className="break-words whitespace-pre-wrap" data-testid="draft-text">
      {parts}
    </p>
  );
}

/** Why the assistant decided this way: one chip per reason code. */
export function ReasonChips({ reasons }: { reasons: string[] }) {
  const { t, i18n } = useTranslation();
  if (reasons.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label={t("convo.draft.reasons")}>
      {reasons.map((code) => (
        <li
          key={code}
          className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-800 ring-1 ring-slate-300 ring-inset"
        >
          {i18n.exists(`convo.reason.${code}`) ? t(`convo.reason.${code}`) : code}
        </li>
      ))}
    </ul>
  );
}

/** Time left to answer (Instagram allows 24 hours after the customer's last message). */
export function WindowTimer({ endsAt }: { endsAt: string | null }) {
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  if (!endsAt) return null;
  const minutes = Math.floor((new Date(endsAt).getTime() - now) / 60_000);
  if (minutes <= 0) return <span className="text-sm text-red-700">{t("convo.window.closed")}</span>;
  const label =
    minutes >= 60
      ? t("convo.window.hours", { count: Math.floor(minutes / 60) })
      : t("convo.window.minutes", { count: minutes });
  return (
    <span className={`text-sm ${minutes < 120 ? "text-amber-800" : "text-slate-600"}`} data-testid="window-timer">
      {label}
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
    <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700" data-testid="approval-state" data-approval-status={state.status}>
      <p>{line}</p>
      {state.decision_note ? (
        <p className="mt-1">{t("convo.draft.approvalState.note", { note: state.decision_note })}</p>
      ) : null}
    </div>
  );
}
