import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Fact } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CheckIcon, ChevronRightIcon, SparkIcon } from "@/components/icons";
import { FOCUS, Panel, PanelHeading, SkeletonRows } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FactStatusChip } from "./FactStatusChip";
import { useFactTransition } from "./hooks";
import { CategoryGlyph } from "./CategoryGlyph";
import { knowledgeBase } from "./useKnowledgeBase";
import { pickLabel } from "./labels";
import { factAnchor, type AttentionItem } from "./model";
import { requirementPath } from "./readinessLinks";

const VISIBLE = 5;

/**
 * The owner's to-do list for knowledge: what blocks setup, suggestions to decide, and facts that
 * are not used until someone looks at them. Verifying here is the same explicit, version-bound
 * call as on the category page; contested facts go to the suggestion that explains them.
 */
export function AttentionPanel({ items, canVerify }: { items: AttentionItem[] | null; canVerify: boolean }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const transition = useFactTransition(workspace.id);
  const [expanded, setExpanded] = useState(false);
  const busyId = transition.isPending ? transition.variables?.factId : undefined;

  const verify = (fact: Fact) =>
    transition.mutate({ factId: fact.id, action: "verify", expectedVersion: fact.current_version });

  if (items !== null && items.length === 0) {
    return (
      <section
        id="knowledge-attention"
        aria-labelledby="knowledge-attention-title"
        data-testid="knowledge-attention"
        className="flex min-w-0 items-start gap-3 rounded-2xl border border-border bg-surface px-4 py-3.5 sm:px-5"
      >
        <span aria-hidden="true" className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-success-subtle text-base text-success">
          <CheckIcon />
        </span>
        <div className="min-w-0">
          <h2 id="knowledge-attention-title" className="font-heading text-base leading-snug font-semibold tracking-tight text-primary">
            {t("knowledge.attention.clear")}
          </h2>
          <p className="text-metadata text-secondary">{t("knowledge.attention.clearHint")}</p>
        </div>
      </section>
    );
  }

  const shown = items && !expanded ? items.slice(0, VISIBLE) : items;
  const hidden = (items?.length ?? 0) - (shown?.length ?? 0);

  return (
    <Panel id="knowledge-attention" aria-labelledby="knowledge-attention-title" data-testid="knowledge-attention" className="gap-3">
      <PanelHeading
        id="knowledge-attention-title"
        icon={<AlertIcon />}
        title={t("knowledge.attention.title")}
        meta={items ? t("knowledge.attention.meta", { count: items.length }) : undefined}
      />
      {transition.error ? <ErrorMessage error={transition.error} /> : null}
      {items === null ? <SkeletonRows label={t("common.loading")} rows={3} /> : null}
      {shown ? (
        <ul className="-mx-2 flex flex-col">
          {shown.map((item) => (
            <AttentionRow
              key={item.kind === "needed" ? `needed-${item.requirement.code}` : item.kind === "fact" ? item.fact.id : "suggestions"}
              item={item}
              canVerify={canVerify}
              busyId={busyId}
              onVerify={verify}
            />
          ))}
        </ul>
      ) : null}
      {items && items.length > VISIBLE ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className={`-mb-1 inline-flex min-h-11 items-center self-start rounded-control px-1 text-metadata font-semibold text-action hover:text-action-hover ${FOCUS}`}
        >
          {expanded ? t("knowledge.attention.less") : t("knowledge.attention.more", { count: hidden })}
        </button>
      ) : null}
    </Panel>
  );
}

function AttentionRow({
  item,
  canVerify,
  busyId,
  onVerify,
}: {
  item: AttentionItem;
  canVerify: boolean;
  busyId: string | undefined;
  onVerify: (fact: Fact) => void;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const base = knowledgeBase(workspace.id);

  if (item.kind === "needed") {
    const { requirement, pendingFact } = item;
    const anchorKey = pendingFact?.key ?? requirement.link.key;
    const path = requirementPath(workspace.id, requirement.link) ?? base;
    const to = anchorKey && !anchorKey.endsWith("*") ? `${path}#${factAnchor(anchorKey)}` : path;
    return (
      <Row
        testId={`attention-needed-${requirement.code}`}
        glyph={requirement.link.category ? <CategoryGlyph category={requirement.link.category as Fact["category"]} tone="attention" size="sm" /> : null}
        title={t(`readiness.requirement.${requirement.code}`)}
        status={<FactStatusChip state="needed" />}
        detail={
          pendingFact
            ? t("knowledge.attention.pendingValue", { value: pendingFact.display })
            : t(`knowledge.attention.needed.${requirement.required_for}`)
        }
        actions={
          <>
            {pendingFact && canVerify && pendingFact.state === "unverified" ? (
              <VerifyButton fact={pendingFact} busy={busyId === pendingFact.id} onVerify={onVerify} />
            ) : null}
            <RowLink to={to}>{pendingFact ? t("knowledge.attention.open") : t("knowledge.actions.add")}</RowLink>
          </>
        }
      />
    );
  }

  if (item.kind === "suggestions") {
    const names = [...new Set(item.candidates.map((c) => pickLabel(c.fact_label, i18n.language)))];
    const preview = names.slice(0, 3).join(", ") + (names.length > 3 ? "…" : "");
    return (
      <Row
        testId="attention-suggestions"
        glyph={
          <span aria-hidden="true" className="flex size-7 shrink-0 items-center justify-center rounded-md bg-assistant text-[0.9375rem] text-action">
            <SparkIcon />
          </span>
        }
        title={t("knowledge.suggestions.waiting", { count: item.candidates.length })}
        detail={preview}
        actions={<RowLink to={`${base}/suggestions`}>{t("knowledge.attention.review")}</RowLink>}
      />
    );
  }

  const { fact } = item;
  const to =
    fact.state === "contested" ? `${base}/suggestions` : `${base}/${fact.category}#${factAnchor(fact.key)}`;
  return (
    <Row
      testId={`attention-fact-${fact.key}`}
      glyph={<CategoryGlyph category={fact.category} size="sm" />}
      title={pickLabel(fact.label, i18n.language)}
      status={<FactStatusChip state={fact.state} />}
      detail={
        <>
          <span className="font-medium text-primary">{fact.display}</span>
          <span aria-hidden="true"> · </span>
          {t(`knowledge.attention.fact.${fact.state}`, { defaultValue: "" })}
        </>
      }
      actions={
        <>
          {fact.state === "unverified" && canVerify ? (
            <VerifyButton fact={fact} busy={busyId === fact.id} onVerify={onVerify} />
          ) : null}
          <RowLink to={to}>
            {fact.state === "contested" ? t("knowledge.attention.decide") : t("knowledge.attention.open")}
          </RowLink>
        </>
      }
    />
  );
}

function Row({
  testId,
  glyph,
  title,
  status,
  detail,
  actions,
}: {
  testId: string;
  glyph: ReactNode;
  title: string;
  status?: ReactNode;
  detail: ReactNode;
  actions: ReactNode;
}) {
  return (
    <li
      data-testid={testId}
      className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 rounded-xl px-2 py-2.5 transition-colors hover:bg-surface-subtle/60 [&+&]:border-t [&+&]:border-border/70"
    >
      <div className="flex min-w-[12rem] flex-1 items-start gap-3">
        <span className="mt-0.5">{glyph}</span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
            <p className="min-w-0 text-body leading-5 font-semibold [overflow-wrap:anywhere] text-primary">{title}</p>
            {status}
          </div>
          <p className="mt-0.5 line-clamp-2 text-metadata [overflow-wrap:anywhere] text-secondary">{detail}</p>
        </div>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-1.5">{actions}</div>
    </li>
  );
}

function RowLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className={`group/link inline-flex min-h-11 min-w-11 items-center justify-center gap-0.5 rounded-control px-2 text-metadata font-semibold text-action transition-colors hover:text-action-hover ${FOCUS}`}
    >
      {/* Phones keep the row on one line: the word stays for screen readers, the chevron shows. */}
      <span className="sr-only underline-offset-4 group-hover/link:underline sm:not-sr-only">{children}</span>
      <ChevronRightIcon aria-hidden="true" className="text-base transition-transform duration-150 group-hover/link:translate-x-0.5" />
    </Link>
  );
}

function VerifyButton({ fact, busy, onVerify }: { fact: Fact; busy: boolean; onVerify: (fact: Fact) => void }) {
  const { t, i18n } = useTranslation();
  return (
    <Button
      variant="secondary"
      disabled={busy}
      aria-label={t("knowledge.attention.verifyNamed", { name: pickLabel(fact.label, i18n.language) })}
      onClick={() => onVerify(fact)}
    >
      <CheckIcon className="text-sm text-success" />
      {busy ? t("knowledge.actions.verifying") : t("knowledge.actions.verify")}
    </Button>
  );
}
