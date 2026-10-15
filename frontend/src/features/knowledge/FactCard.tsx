import { useTranslation } from "react-i18next";
import type { Fact } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { FactStatusChip } from "./FactStatusChip";
import { pickLabel } from "./labels";

interface Props {
  fact: Fact;
  timezone: string;
  canVerify: boolean;
  busy: boolean;
  onEdit: () => void;
  onHistory: () => void;
  onVerify: () => void;
  onRestore: () => void;
}

/** One fact: label, value as the customer would see it, status, source and verification date. */
export function FactCard({ fact, timezone, canVerify, busy, onEdit, onHistory, onVerify, onRestore }: Props) {
  const { t, i18n } = useTranslation();
  const date = (iso: string) =>
    new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeZone: timezone }).format(new Date(iso));
  const archived = fact.status === "archived";
  const validity =
    fact.valid_from || fact.valid_until
      ? t("knowledge.validity", {
          from: fact.valid_from ?? "…",
          until: fact.valid_until ?? "…",
        })
      : null;

  return (
    <Card className="flex flex-col gap-2" data-testid={`fact-${fact.key}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="min-w-0 text-base font-semibold break-words">{pickLabel(fact.label, i18n.language)}</h3>
        <FactStatusChip state={fact.state} />
      </div>
      <p className="text-base break-words whitespace-pre-line">{fact.display}</p>
      {validity ? <p className="text-sm text-slate-600">{validity}</p> : null}
      {fact.status === "verified" && fact.last_verified_at ? (
        <p className="text-sm text-slate-600">
          {t("knowledge.verifiedOn", { date: date(fact.last_verified_at) })}
          {fact.source_type ? ` · ${t(`knowledge.source.${fact.source_type}`, { defaultValue: fact.source_type })}` : ""}
          {fact.last_verified_by_name ? ` · ${fact.last_verified_by_name}` : ""}
        </p>
      ) : null}
      {fact.state === "contested" ? (
        <p className="text-sm text-orange-900">{t("knowledge.contestedNote")}</p>
      ) : null}
      {fact.state === "unverified" ? (
        <p className="text-sm text-amber-900">{t("knowledge.unverifiedNote")}</p>
      ) : null}
      <div className="mt-1 flex flex-wrap gap-2">
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
                {busy ? t("knowledge.actions.verifying") : t("knowledge.actions.verify")}
              </Button>
            ) : null}
            <Button variant="secondary" onClick={onEdit}>
              {canVerify ? t("knowledge.actions.edit") : t("knowledge.actions.suggestChange")}
            </Button>
          </>
        )}
        <Button variant="ghost" onClick={onHistory}>
          {t("knowledge.actions.history")}
        </Button>
      </div>
    </Card>
  );
}
