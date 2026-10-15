import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { ErrorMessage } from "@/components/ErrorMessage";
import { FullScreenStatus } from "@/components/FullScreenStatus";
import { Button } from "@/components/Button";
import { useMe } from "./hooks";

/** Auth guard: renders the child routes only for a signed-in user. */
export function RequireAuth() {
  const { t } = useTranslation();
  const me = useMe();
  const location = useLocation();

  if (me.isPending) return <FullScreenStatus>{t("common.loading")}</FullScreenStatus>;
  if (me.isError) {
    return (
      <FullScreenStatus>
        <ErrorMessage error={me.error} />
        <Button onClick={() => void me.refetch()}>{t("common.retry")}</Button>
      </FullScreenStatus>
    );
  }
  if (me.data === null) return <Navigate to="/login" replace state={{ from: location }} />;
  return <Outlet />;
}
