import { useTranslation } from "react-i18next";
import { localizeError } from "@/api/errors";

/** What happened and what to do, in the user's language, from the error code. */
export function ErrorMessage({ error }: { error: unknown }) {
  const { t } = useTranslation();
  const { what, next, requestId } = localizeError(error, t);
  return (
    <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300">
      <p className="font-medium">{what}</p>
      <p>{next}</p>
      {requestId ? (
        <p className="mt-1 text-xs break-all text-red-800">{t("errors.requestId", { id: requestId })}</p>
      ) : null}
    </div>
  );
}
