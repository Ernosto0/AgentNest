import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Readiness } from "@/api/types";
import { CheckIcon, AlertIcon, ChevronRightIcon } from "@/components/icons";
import { requirementPath } from "./readinessLinks";

/** The checklist behind the readiness level; each open item links to where it is fixed. */
export function ReadinessChecklist({
  workspaceId,
  readiness,
  onlyOpen = false,
}: {
  workspaceId: string;
  readiness: Readiness;
  onlyOpen?: boolean;
}) {
  const { t } = useTranslation();
  const items = readiness.requirements.filter((r) => !onlyOpen || !r.satisfied);
  return (
    <ul className="flex flex-col gap-1">
      {items.map((requirement) => {
        const path = requirement.satisfied ? null : requirementPath(workspaceId, requirement.link);
        const label = t(`readiness.requirement.${requirement.code}`);
        const body = (
          <>
            {requirement.satisfied ? (
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-control bg-success-subtle text-success">
                <CheckIcon className="text-base" />
              </span>
            ) : (
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-control bg-attention-subtle text-attention">
                <AlertIcon className="text-base" />
              </span>
            )}
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-primary text-sm">{label}</span>
              {requirement.satisfied ? null : (
                <span className="block text-xs text-secondary mt-0.5">
                  {t(`readiness.status.${requirement.status}`)}
                </span>
              )}
            </span>
            {path ? <ChevronRightIcon className="shrink-0 text-xl text-secondary" /> : null}
          </>
        );
        const className =
          "flex min-h-11 items-center gap-3 rounded-control px-3 py-2 text-left text-base text-primary";
        return (
          <li key={requirement.code} data-requirement={requirement.code} data-satisfied={requirement.satisfied}>
            {path ? (
              <Link
                to={path}
                className={`${className} hover:bg-surface-subtle transition-colors focus-visible:outline-2 focus-visible:outline-focus`}
              >
                {body}
              </Link>
            ) : (
              <div className={className}>{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
