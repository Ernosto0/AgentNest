import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { CancelAction } from "./CancelAction";
import { ScheduleSheet } from "./ScheduleSheet";

const KNOWN_REASONS = ["FACT_CHANGED", "ACCOUNT_UNAVAILABLE"] as const;
type Reason = (typeof KNOWN_REASONS)[number];

const isKnown = (reason: string | null): reason is Reason =>
  reason !== null && (KNOWN_REASONS as readonly string[]).includes(reason);

/**
 * An item the system held back (`FACT_CHANGED`: a fact it uses changed; `ACCOUNT_UNAVAILABLE`:
 * Instagram could not be reached with the account). Says why, and offers what can be done:
 * edit it, approve it again as it is (owner or manager; checked again by the server, and the
 * new approval binds the next version), or cancel it. Staff can only edit.
 */
export function OnHoldActions({ item, onEdit }: { item: ContentItem; onEdit: () => void }) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canApprove = role === "owner" || role === "manager";
  const [reapproving, setReapproving] = useState(false);
  const reason = isKnown(item.hold_reason) ? item.hold_reason : "unknown";
  const base = `/w/${workspace.id}`;
  const linkClass =
    "inline-flex min-h-11 items-center font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-focus";

  return (
    <section
      aria-label={t("content.hold.title")}
      data-testid="on-hold"
      data-reason={item.hold_reason ?? "unknown"}
      className="flex flex-col gap-3 rounded-panel border border-attention bg-attention-subtle p-4 text-attention shadow-xs"
    >
      <h2 className="font-heading font-semibold">{t("content.hold.title")}</h2>
      <p>{t(`content.hold.${reason}.what`)}</p>
      <p>{t(`content.hold.${reason}.next`)}</p>

      {reason === "FACT_CHANGED" ? (
        <Link to={`${base}/more/knowledge`} className={linkClass}>
          {t("content.hold.openKnowledge")}
        </Link>
      ) : null}
      {reason === "ACCOUNT_UNAVAILABLE" ? (
        <Link to={`${base}/more/settings/connections`} className={linkClass}>
          {t("content.hold.openConnection")}
        </Link>
      ) : null}

      {!canApprove ? <p className="text-sm opacity-90">{t("content.hold.staffNote")}</p> : null}

      <div className="flex flex-wrap items-start gap-2 pt-1">
        <Button variant="secondary" onClick={onEdit}>
          {t("content.actions.edit")}
        </Button>
        {canApprove ? <Button onClick={() => setReapproving(true)}>{t("content.hold.reapprove")}</Button> : null}
        <CancelAction item={item} />
      </div>

      {reapproving ? (
        <ScheduleSheet
          item={item}
          mode="reapprove"
          onClose={() => setReapproving(false)}
          onEditText={() => {
            setReapproving(false);
            // After the sheet has closed and handed focus back to its opener.
            window.setTimeout(onEdit, 0);
          }}
        />
      ) : null}
    </section>
  );
}
