import { useId } from "react";
import { workspaceSwitchTarget } from "@/app/layout/navigation";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useMe } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "./context";

/** Switch to another workspace, staying on the same section when it exists there. */
export function WorkspaceSwitcher() {
  const { t } = useTranslation();
  const id = useId();
  const navigate = useNavigate();
  const location = useLocation();
  const me = useMe();
  const { workspace } = useCurrentWorkspace();
  const memberships = me.data?.memberships ?? [];

  return (
    <div className="min-w-0">
      <label htmlFor={id} className="sr-only">
        {t("workspaces.switcherLabel")}
      </label>
      <select
        id={id}
        value={workspace.id}
        onChange={(event) =>
          void navigate(workspaceSwitchTarget(location.pathname, location.search, workspace.id, event.target.value))
        }
        className="min-h-11 w-full max-w-40 min-[1200px]:max-w-64 min-w-0 truncate rounded-lg border border-control bg-surface px-3 text-base text-primary focus-visible:outline-2 focus-visible:outline-focus"
      >
        {memberships.map((m) => (
          <option key={m.workspace_id} value={m.workspace_id}>
            {m.workspace_name}
          </option>
        ))}
      </select>
    </div>
  );
}
