import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";

/** Shown for unknown routes and for workspaces the user cannot access (404, never 403). */
export function NotFoundPage({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation();
  const Container = embedded ? "section" : "main";
  return (
    <Container className={`mx-auto flex w-full max-w-md flex-col justify-center px-4 py-8 ${embedded ? "min-h-[50dvh]" : "min-h-dvh"}`}>
      <EmptyState
        titleAs="h1"
        title={t("notFound.title")}
        description={t("notFound.body")}
        action={
          <Link
            to="/"
            className="inline-flex min-h-11 items-center rounded-control px-4 font-medium text-action hover:underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-focus transition-colors"
          >
            {t("notFound.back")}
          </Link>
        }
      />
    </Container>
  );
}
