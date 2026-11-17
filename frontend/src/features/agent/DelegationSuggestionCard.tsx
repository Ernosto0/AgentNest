import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CheckIcon, SparkIcon } from "@/components/icons";
import { Panel, PanelHeading } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useApplyLadder, useDismissLadder, useLadderSuggestions, usePreviewLadder, type LadderSuggestion } from "./ladderHooks";

/**
 * The weekly "send these replies automatically?" suggestion (D-02, approval ladder), for the
 * owner only. It never changes anything by itself: "Review" opens the existing delegation preview
 * for the exact change the server proposed, and only the second button applies that same change.
 * "Not now" records a cool-down. `accountId` limits the card to one account (the Assistant page).
 */
export function DelegationSuggestionCard({ accountId }: { accountId?: string }) {
  const { workspace, role } = useCurrentWorkspace();
  const suggestions = useLadderSuggestions(workspace.id, role === "owner");
  // The list refetches after a confirmation and no longer holds the suggestion, so the card
  // remembers what it turned on to say so (and to link to the settings) until the page changes.
  const [accepted, setAccepted] = useState<{ id: string; intent: string } | null>(null);
  const first = suggestions.data?.find((s) => accountId === undefined || s.account_id === accountId);
  if (accepted) return <AcceptedPanel intent={accepted.intent} id={accepted.id} />;
  if (!first) return null;
  // Keyed by id: a new week's suggestion starts again at "Review", never at "Turn on".
  return <SuggestionPanel key={first.id} suggestion={first} onAccepted={() => setAccepted({ id: first.id, intent: first.intent })} />;
}

function AcceptedPanel({ id, intent }: { id: string; intent: string }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const topic = t(`ladder.topic.${intent}`, { defaultValue: intent });
  return (
    <Panel tone="assistant" aria-labelledby={`ladder-${id}`} data-testid="ladder-done" className="gap-3">
      <PanelHeading id={`ladder-${id}`} icon={<CheckIcon />} iconTone="assistant" title={t("ladder.done", { topic })} />
      <Link className="self-start text-body font-medium text-action hover:underline" to={`/w/${workspace.id}/more/automation`}>
        {t("ladder.settings")}
      </Link>
    </Panel>
  );
}

function SuggestionPanel({ suggestion, onAccepted }: { suggestion: LadderSuggestion; onAccepted: () => void }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const preview = usePreviewLadder(workspace.id, suggestion.account_id);
  const apply = useApplyLadder(workspace.id, suggestion.account_id, onAccepted);
  const dismiss = useDismissLadder(workspace.id);
  const [reviewed, setReviewed] = useState(false);
  const topicKey = `ladder.topic.${suggestion.intent}`;
  const topic = t(topicKey, { defaultValue: suggestion.intent });
  const error = preview.error ?? apply.error ?? dismiss.error;
  const busy = preview.isPending || apply.isPending || dismiss.isPending;

  return (
    <Panel tone="assistant" aria-labelledby={`ladder-${suggestion.id}`} data-testid="ladder-card" className="gap-3">
      <PanelHeading
        id={`ladder-${suggestion.id}`}
        icon={<SparkIcon />}
        iconTone="assistant"
        title={reviewed ? t("ladder.confirmTitle", { topic }) : t("ladder.title", { topic })}
      />
      <p className="text-body text-secondary">
        {reviewed
          ? t("ladder.confirmBody", { topic })
          : t("ladder.body", { days: suggestion.window_days, count: suggestion.counts.unchanged ?? 0, topic })}
      </p>
      {reviewed ? null : <p className="text-metadata text-secondary">{t("ladder.note")}</p>}
      {error ? <ErrorMessage error={error} /> : null}
      <div className="flex flex-wrap items-center gap-2">
        {reviewed ? (
          <>
            <Button
              pending={apply.isPending}
              disabled={busy}
              onClick={() => apply.mutate(suggestion.change)}
            >
              {apply.isPending ? t("ladder.confirming") : t("ladder.confirm")}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => setReviewed(false)}>
              {t("ladder.back")}
            </Button>
          </>
        ) : (
          <>
            <Button
              pending={preview.isPending}
              disabled={busy}
              onClick={() => preview.mutate(suggestion.change, { onSuccess: () => setReviewed(true) })}
            >
              {preview.isPending ? t("ladder.reviewing") : t("ladder.review")}
            </Button>
            <Button variant="secondary" pending={dismiss.isPending} disabled={busy} onClick={() => dismiss.mutate(suggestion.id)}>
              {dismiss.isPending ? t("ladder.dismissing") : t("ladder.dismiss")}
            </Button>
          </>
        )}
      </div>
      {reviewed ? null : <p className="text-metadata text-secondary">{t("ladder.dismissHint")}</p>}
    </Panel>
  );
}
