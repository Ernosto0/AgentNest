import { useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Role } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { TextField } from "@/components/TextField";
import { MORE_GROUPS, NAV_ITEMS, allowedDestination, workspaceTarget } from "./navigation";

export function DestinationLauncher({ workspaceId, role, demoTools, onClose, returnFocusRef }: {
  workspaceId: string; role: Role; demoTools: boolean; onClose: () => void; returnFocusRef?: RefObject<HTMLElement | null>;
}) {
  const { t, i18n } = useTranslation();
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const results = useRef<HTMLDivElement>(null);
  const destinations = [...NAV_ITEMS, ...MORE_GROUPS.flatMap(group => group.items)]
    .filter((item, index, all) => all.findIndex(other => other.path === item.path) === index)
    .filter(item => allowedDestination(item, role, demoTools))
    .filter(item => t(item.labelKey).toLocaleLowerCase(i18n.language).includes(query.trim().toLocaleLowerCase(i18n.language)));

  function keyboard(event: KeyboardEvent<HTMLDivElement>) {
    const links = Array.from(results.current?.querySelectorAll<HTMLAnchorElement>("a") ?? []);
    if (event.key === "Enter" && event.target === input.current && links[0]) {
      event.preventDefault(); links[0].click();
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const targets: HTMLElement[] = [input.current, ...links].filter((item): item is HTMLInputElement | HTMLAnchorElement => item !== null);
    const index = targets.indexOf(document.activeElement as HTMLElement);
    targets[(index + (event.key === "ArrowDown" ? 1 : -1) + targets.length) % targets.length]?.focus();
  }

  return <BottomSheet title={t("shell.launcherTitle")} description={t("shell.launcherHint")} onClose={onClose} initialFocusRef={input} returnFocusRef={returnFocusRef}>
    <div onKeyDown={keyboard}>
      <TextField ref={input} label={t("shell.filterDestinations")} type="text" value={query} onChange={event => setQuery(event.target.value)} autoComplete="off" />
      <div ref={results} className="mt-4">
        <ul className="flex flex-col gap-1">
          {destinations.map(({ path, labelKey, icon: Icon }) => <li key={path}>
            <Link to={workspaceTarget(workspaceId, path)} onClick={onClose} className="flex min-h-11 items-center gap-3 rounded-control px-3 py-2 text-form text-primary hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-focus"><Icon className="shrink-0 text-xl" />{t(labelKey)}</Link>
          </li>)}
        </ul>
        {!destinations.length ? <p className="py-4 text-body text-secondary" role="status">{t("shell.noDestination")}</p> : null}
      </div>
    </div>
  </BottomSheet>;
}
