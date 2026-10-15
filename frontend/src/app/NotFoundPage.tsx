import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";

/** Shown for unknown routes and for workspaces the user cannot access (404, never 403). */
export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-4 py-8">
      <EmptyState
        titleAs="h1"
        title={t("notFound.title")}
        description={t("notFound.body")}
        action={
          <Link
            to="/"
            className="inline-flex min-h-11 items-center rounded-lg px-4 font-medium text-indigo-800 underline"
          >
            {t("notFound.back")}
          </Link>
        }
      />
    </main>
  );
}
