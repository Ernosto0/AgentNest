import { useTranslation } from "react-i18next";
import { localizeError } from "@/api/errors";

/** What happened and what to do, in the user's language, from the error code. */
export function ErrorMessage({ error }: { error: unknown }) {
  const { t } = useTranslation();
  const { what, next, requestId } = localizeError(error, t);
  return (
    <div role="alert" className="min-w-0 rounded-control border border-danger bg-danger-subtle p-4 text-body text-danger">
      <p className="font-medium">{what}</p>
      <p>{next}</p>
      {requestId ? (
        <p className="mt-2 text-metadata break-all">{t("errors.requestId", { id: requestId })}</p>
      ) : null}
    </div>
  );
}
