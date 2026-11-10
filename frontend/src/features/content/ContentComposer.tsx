import { useId, useState, type Ref } from "react";
import { useTranslation } from "react-i18next";
import type { ContentType } from "@/api/types";
import { Button } from "@/components/Button";
import { PlusIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import type { NewContentMode } from "./GenerateSheet";
import { OBJECTIVE_MAX } from "./limits";

export type StartContent = (mode: NewContentMode, type: ContentType, objective?: string) => void;

const TYPES: readonly ContentType[] = ["feed_image", "story_image"];

/**
 * The page's one place to start content. A brief typed here opens the existing draft sheet with
 * it filled in (nothing is generated until the owner sends it there); an empty brief opens the
 * sheet as before. A blank draft is the quieter alternative, so the AI is never the only way in.
 */
export function ContentComposer({ onStart, inputRef }: { onStart: StartContent; inputRef?: Ref<HTMLInputElement> }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const accounts = useSocialAccounts(workspace.id);
  const account = accounts.data?.find((candidate) => candidate.status !== "disconnected") ?? null;
  const ids = { title: useId(), input: useId(), hint: useId() };
  const [objective, setObjective] = useState("");
  const [type, setType] = useState<ContentType>("feed_image");

  return (
    <section aria-labelledby={ids.title} data-testid="content-composer" className="rounded-2xl bg-assistant p-3 sm:p-4">
      <h2 id={ids.title} className="sr-only">
        {t("content.composer.title")}
      </h2>
      <form
        className="flex flex-col gap-3 lg:flex-row lg:items-center"
        onSubmit={(event) => {
          event.preventDefault();
          onStart("ai", type, objective.trim());
          setObjective("");
        }}
      >
        <div className="flex min-w-0 flex-1 items-center gap-3 rounded-xl bg-surface py-1 pr-1.5 pl-2 ring-1 ring-border transition-shadow focus-within:ring-2 focus-within:ring-action">
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-action text-base text-on-action">
            <SparkIcon />
          </span>
          <label htmlFor={ids.input} className="sr-only">
            {t("content.composer.inputLabel")}
          </label>
          <input
            ref={inputRef}
            id={ids.input}
            value={objective}
            maxLength={OBJECTIVE_MAX}
            onChange={(event) => setObjective(event.target.value)}
            placeholder={t("content.composer.placeholder")}
            aria-describedby={ids.hint}
            autoComplete="off"
            className="min-h-11 min-w-0 flex-1 bg-transparent text-form text-primary placeholder:text-secondary/80 focus:outline-none"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <fieldset className="flex shrink-0">
            <legend className="sr-only">{t("content.composer.typeLabel")}</legend>
            <div className="inline-flex rounded-xl bg-surface/70 p-1 ring-1 ring-border/70">
              {TYPES.map((option) => (
                <label
                  key={option}
                  className={`relative inline-flex min-h-11 cursor-pointer md:min-h-9 items-center rounded-lg px-3 text-metadata font-semibold transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-focus ${
                    type === option ? "bg-surface text-primary shadow-xs ring-1 ring-border" : "text-secondary hover:text-primary"
                  }`}
                >
                  <input
                    type="radio"
                    name={`${ids.input}-type`}
                    value={option}
                    checked={type === option}
                    onChange={() => setType(option)}
                    className="sr-only"
                  />
                  {t(`content.type.${option}`)}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex flex-1 basis-60 flex-wrap items-center gap-2 sm:flex-none sm:basis-auto">
            <Button type="submit" className="flex-1 whitespace-nowrap sm:flex-none">
              <SparkIcon className="text-base" />
              <span>{t("content.actions.newDraft")}</span>
            </Button>
            <Button variant="ghost" onClick={() => onStart("blank", type)} className="flex-1 px-3 whitespace-nowrap hover:bg-surface/70 sm:flex-none">
              <PlusIcon className="text-base" />
              <span>{t("content.actions.blankDraft")}</span>
            </Button>
          </div>
        </div>
      </form>
      <div id={ids.hint} className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-xs text-secondary">
        <span>{t("content.composer.hint")}</span>
        {account ? (
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true">·</span>
            <span>{t("content.composer.account", { account: `@${account.username ?? account.id}` })}</span>
            {account.is_simulated ? <SimulatedBadge compact /> : null}
          </span>
        ) : accounts.isSuccess ? (
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true">·</span>
            <span>{t("content.composer.noAccount")}</span>
          </span>
        ) : null}
      </div>
    </section>
  );
}
