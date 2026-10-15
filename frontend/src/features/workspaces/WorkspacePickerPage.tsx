import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ChevronRightIcon } from "@/components/icons";
import { EmptyState } from "@/components/EmptyState";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useLogout, useMe, useSaveLocale } from "@/features/auth/hooks";

export function WorkspacePickerPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const logout = useLogout();
  const saveLocale = useSaveLocale();
  const memberships = me.data?.memberships ?? [];

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col gap-6 px-4 py-8">
      <div className="flex items-center justify-between gap-3">
        <LanguageSwitch onChange={(language) => saveLocale.mutate(language)} />
        <Button
          variant="ghost"
          disabled={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
        >
          {logout.isPending ? t("auth.signingOut") : t("auth.signOut")}
        </Button>
      </div>
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{t("workspaces.pickerTitle")}</h1>
        <p className="mt-1 text-slate-600">{t("workspaces.pickerHint")}</p>
      </div>
      {memberships.length === 0 ? (
        <EmptyState title={t("workspaces.none")} />
      ) : (
        <ul className="flex flex-col gap-3">
          {memberships.map((m) => (
            <li key={m.workspace_id}>
              <Link
                to={`/w/${m.workspace_id}`}
                className="block rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
              >
                <Card className="flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-base font-medium text-slate-900">{m.workspace_name}</p>
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600">
                      <span>{t(`workspaces.role.${m.role}`)}</span>
                      {m.is_demo ? <SimulatedBadge /> : null}
                    </p>
                  </div>
                  <ChevronRightIcon className="text-xl text-slate-400" />
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
