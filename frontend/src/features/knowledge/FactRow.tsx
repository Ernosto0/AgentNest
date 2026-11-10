import { useTranslation } from "react-i18next";
import type { Fact, TemplateItem } from "@/api/types";
import { Button } from "@/components/Button";
import { AlertIcon, CheckIcon, ClockIcon, PauseIcon, PencilIcon, PlusIcon } from "@/components/icons";
import { FactStatusChip } from "./FactStatusChip";
import { pickLabel } from "./labels";
import { factAnchor, itemAnchor } from "./model";

interface FactRowProps {
  fact: Fact;
  timezone: string;
  canVerify: boolean;
  busy: boolean;
  /** This fact is what a setup requirement is waiting for. */
  needed: boolean;
  onEdit: () => void;
  onHistory: () => void;
  onVerify: () => void;
  onRestore: () => void;
}

/**
 * One fact as a row: label and status, the value as customers see it, then where it came from
 * and when it was verified. Verify is the primary action only while a fact is unverified.
 */
export function FactRow({ fact, timezone, canVerify, busy, needed, onEdit, onHistory, onVerify, onRestore }: FactRowProps) {
  const { t, i18n } = useTranslation();
  const date = (iso: string) =>
    new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeZone: timezone }).format(new Date(iso));
  const archived = fact.status === "archived";
  const validity =
    fact.valid_from || fact.valid_until
      ? t("knowledge.validity", { from: fact.valid_from ?? "…", until: fact.valid_until ?? "…" })
      : null;
  const provenance = [
    fact.status === "verified" && fact.last_verified_at ? t("knowledge.verifiedOn", { date: date(fact.last_verified_at) }) : null,
    fact.source_type ? t(`knowledge.source.${fact.source_type}`, { defaultValue: fact.source_type }) : null,
    fact.status === "verified" ? fact.last_verified_by_name : null,
  ].filter(Boolean);
  const note =
    fact.state === "contested"
      ? { icon: PauseIcon, text: t("knowledge.contestedNote") }
      : fact.state === "unverified"
        ? { icon: ClockIcon, text: t("knowledge.unverifiedNote") }
        : fact.state === "expired"
          ? { icon: AlertIcon, text: t("knowledge.expiredNote") }
          : null;

  return (
    <li
      id={factAnchor(fact.key)}
      data-testid={`${archived ? "archived-fact" : "fact"}-${fact.key}`}
      className="group/row relative flex min-w-0 scroll-mt-24 flex-col gap-3 px-4 py-4 transition-colors data-[highlight=true]:bg-assistant/60 sm:px-5 lg:flex-row lg:items-start lg:gap-6"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
          <h3 className="min-w-0 text-body leading-5 font-semibold [overflow-wrap:anywhere] text-secondary">
            {pickLabel(fact.label, i18n.language)}
          </h3>
          <FactStatusChip state={fact.state} quiet={fact.state === "verified"} />
          {needed ? <FactStatusChip state="needed" /> : null}
        </div>
        <p className={`text-base leading-relaxed font-medium [overflow-wrap:anywhere] whitespace-pre-line ${archived ? "text-secondary" : "text-primary"}`}>
          {fact.display}
        </p>
        {validity ? <p className="text-metadata text-secondary">{validity}</p> : null}
        {provenance.length > 0 ? <p className="text-xs text-secondary">{provenance.join(" · ")}</p> : null}
        {note ? (
          <p className="mt-1 flex items-start gap-2 rounded-lg bg-attention-subtle px-3 py-2 text-metadata font-medium text-attention">
            <note.icon aria-hidden="true" className="mt-0.5 shrink-0" />
            <span>{note.text}</span>
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 lg:justify-end">
        {archived ? (
          canVerify ? (
            <Button variant="secondary" disabled={busy} onClick={onRestore}>
              {t("knowledge.actions.restore")}
            </Button>
          ) : null
        ) : (
          <>
            {fact.state === "unverified" && canVerify ? (
              <Button disabled={busy} onClick={onVerify}>
                <CheckIcon className="text-base" />
                {busy ? t("knowledge.actions.verifying") : t("knowledge.actions.verify")}
              </Button>
            ) : null}
            <Button variant="secondary" onClick={onEdit}>
              <PencilIcon className="text-sm text-secondary" />
              {canVerify ? t("knowledge.actions.edit") : t("knowledge.actions.suggestChange")}
            </Button>
          </>
        )}
        <Button variant="ghost" onClick={onHistory} className="text-secondary">
          {t("knowledge.actions.history")}
        </Button>
      </div>
    </li>
  );
}

/** A suggested template item with no fact: what it is, whether setup waits for it, and Add. */
export function NotAddedRow({
  item,
  needed,
  oneOf = false,
  canVerify,
  onAdd,
}: {
  item: TemplateItem;
  needed: boolean;
  /** Needed, but any one of its group is enough (a phone, WhatsApp or email). */
  oneOf?: boolean;
  canVerify: boolean;
  /** Absent when this role cannot add it (staff cannot name new services or prices). */
  onAdd?: () => void;
}) {
  const { t, i18n } = useTranslation();
  return (
    <li
      id={itemAnchor(item.identifier)}
      data-testid={`missing-${item.key ?? item.identifier}`}
      className={`flex min-w-0 scroll-mt-24 flex-col gap-3 rounded-xl border border-dashed px-4 py-3 transition-colors data-[highlight=true]:bg-assistant/60 sm:flex-row sm:items-center sm:justify-between ${
        needed ? "border-attention/50 bg-attention-subtle/40" : "border-border bg-surface"
      }`}
    >
      <div className="flex min-w-0 flex-col gap-0.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
          <h3 className="min-w-0 text-body leading-5 font-semibold [overflow-wrap:anywhere] text-primary">{pickLabel(item.label, i18n.language)}</h3>
          <FactStatusChip state={needed ? (oneOf ? "one_of" : "needed") : "not_added"} />
        </div>
        <p className="text-metadata text-secondary">{pickLabel(item.description, i18n.language)}</p>
      </div>
      {onAdd ? (
        <Button variant={needed && !oneOf ? "primary" : "secondary"} onClick={onAdd} className="shrink-0 self-start sm:self-center">
          <PlusIcon className="text-base" />
          {canVerify ? t("knowledge.actions.add") : t("knowledge.actions.suggest")}
        </Button>
      ) : null}
    </li>
  );
}
