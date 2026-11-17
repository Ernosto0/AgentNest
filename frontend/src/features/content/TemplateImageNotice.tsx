import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CheckIcon, ImageIcon } from "@/components/icons";
import { pickLabel } from "@/features/knowledge/labels";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useRerenderTemplateImage } from "./templateHooks";

/**
 * Where a template image stands. It says the picture was made from a template; when a fact it
 * shows has changed it warns and offers "re-render with the new value". The re-render makes a new
 * version that is a draft again and needs approval again: this never approves or publishes.
 */
export function TemplateImageNotice({ item }: { item: ContentItem }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const rerender = useRerenderTemplateImage(workspace.id, item.id);
  const [done, setDone] = useState(false);
  const state = item.template_image;
  if (!state) return null;

  const names = state.facts
    .filter((fact) => fact.current_version !== fact.recorded_version || !fact.usable)
    .map((fact) => pickLabel(fact.label, i18n.language) || fact.key)
    .join(", ");

  return (
    <div className="flex flex-col gap-3" data-testid="template-image-notice">
      <p className="inline-flex items-center gap-2 text-xs font-semibold text-secondary" data-testid="template-badge">
        <ImageIcon className="text-sm" />
        <span>{t("content.template.madeFrom", { template: t(`content.template.names.${state.template}`) })}</span>
      </p>
      {done ? (
        <p
          role="status"
          data-testid="template-rerendered"
          className="flex items-start gap-2 rounded-panel border border-success/30 bg-success-subtle p-3.5 text-sm font-semibold text-success"
        >
          <CheckIcon className="mt-0.5 shrink-0 text-base" />
          <span>{t("content.template.stale.done")}</span>
        </p>
      ) : null}
      {state.stale ? (
        <section
          aria-label={t("content.template.stale.title")}
          data-testid="template-stale"
          className="flex flex-col gap-3 rounded-panel border border-attention bg-attention-subtle p-4 text-attention shadow-xs"
        >
          <div className="flex items-start gap-2.5">
            <AlertIcon className="mt-0.5 shrink-0 text-base" />
            <div className="flex flex-col gap-1">
              <h2 className="font-heading text-base font-bold">{t("content.template.stale.title")}</h2>
              <p className="text-sm">{t("content.template.stale.body", { facts: names })}</p>
              {item.status === "on_hold" ? (
                <p className="text-sm opacity-90">{t("content.template.stale.holdHint")}</p>
              ) : null}
            </div>
          </div>
          {state.can_rerender ? (
            <div>
              <Button
                disabled={rerender.isPending}
                pending={rerender.isPending}
                onClick={() => rerender.mutate({ expectedVersion: item.version }, { onSuccess: () => setDone(true) })}
                className="shadow-xs"
              >
                {rerender.isPending ? t("content.template.stale.rerendering") : t("content.template.stale.rerender")}
              </Button>
            </div>
          ) : null}
          {rerender.error ? <ErrorMessage error={rerender.error} /> : null}
        </section>
      ) : null}
    </div>
  );
}
