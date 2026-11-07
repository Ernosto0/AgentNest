import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PublicShell } from "@/app/layout/PublicShell";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";

interface DeletionStatusResult {
  confirmation_code: string;
  status: string;
  requested_at?: string;
  completed_at?: string;
}

export function DataDeletionInfoPage() {
  const { t } = useTranslation();
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<DeletionStatusResult | null>(null);
  const [errorStatus, setErrorStatus] = useState<string | null>(null);

  async function checkStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanCode = code.trim();
    if (!cleanCode) return;

    setPending(true);
    setResult(null);
    setErrorStatus(null);

    try {
      const baseUrl = typeof window !== "undefined" ? window.location.origin : "http://localhost";
      const request = new Request(`${baseUrl}/api/v1/webhooks/meta/data-deletion/${encodeURIComponent(cleanCode)}`, {
        headers: { Accept: "application/json" },
      });
      const response = await fetch(request);
      if (response.status === 404) {
        setErrorStatus(t("legal.dataDeletionStatusNotFound"));
      } else if (!response.ok) {
        setErrorStatus(t("legal.dataDeletionStatusNotFound"));
      } else {
        const data = (await response.json()) as DeletionStatusResult;
        setResult(data);
      }
    } catch {
      setErrorStatus(t("legal.dataDeletionStatusNotFound"));
    } finally {
      setPending(false);
    }
  }

  return (
    <PublicShell
      title={t("legal.dataDeletionTitle")}
      description={t("legal.dataDeletionSubtitle")}
      action={
        <Link to="/login" className="inline-flex min-h-11 items-center rounded-control border border-border bg-surface px-4 text-body font-medium text-primary hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{t("legal.backToLogin")}</Link>
      }
    >
      <div className="flex flex-col gap-6 rounded-panel border border-border bg-surface p-6 sm:p-8 shadow-xs">
        <section className="flex flex-col gap-3">
          <p className="text-sm leading-relaxed text-secondary">{t("legal.dataDeletionOverview")}</p>
          <div className="flex flex-col gap-2 rounded-md bg-canvas/60 p-4 text-xs text-secondary">
            <p>{t("legal.dataDeletionStep1")}</p>
            <p>{t("legal.dataDeletionStep2")}</p>
            <p>{t("legal.dataDeletionStep3")}</p>
          </div>
        </section>

        <section className="flex flex-col gap-4 border-t border-border pt-6">
          <h2 className="font-heading text-base font-semibold text-primary">
            {t("legal.dataDeletionLookupTitle")}
          </h2>
          <form onSubmit={checkStatus} className="flex flex-col gap-3" noValidate>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="flex-1">
                <TextField
                  label={t("legal.dataDeletionLookupTitle")}
                  placeholder={t("legal.dataDeletionLookupPlaceholder")}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  maxLength={100}
                />
              </div>
              <Button type="submit" pending={pending} disabled={!code.trim()}>
                {t("legal.dataDeletionLookupButton")}
              </Button>
            </div>
          </form>

          {errorStatus ? (
            <div role="status" className="rounded-control border border-attention bg-attention-subtle p-3 text-xs text-attention">
              {errorStatus}
            </div>
          ) : null}

          {result ? (
            <div role="status" className="flex min-w-0 flex-col gap-2 break-words rounded-control border border-success bg-success-subtle p-4 text-xs text-success">
              <p className="font-semibold">
                {result.status === "completed"
                  ? t("legal.dataDeletionStatusCompleted")
                  : t("legal.dataDeletionStatusPending")}
              </p>
              <p>
                <strong>{t("legal.codeLabel")}</strong> {result.confirmation_code}
              </p>
              {result.requested_at ? (
                <p>
                  <strong>{t("legal.requestedAtLabel")}</strong> {result.requested_at}
                </p>
              ) : null}
              {result.completed_at ? (
                <p>
                  <strong>{t("legal.completedAtLabel")}</strong> {result.completed_at}
                </p>
              ) : null}
            </div>
          ) : null}
        </section>

        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-4 text-xs text-secondary">
          <Link to="/privacy" className="inline-flex min-h-11 items-center rounded-control hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
            {t("legal.privacyTitle")}
          </Link>
          <Link to="/login" className="inline-flex min-h-11 items-center rounded-control hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
            {t("legal.backToLogin")}
          </Link>
        </div>
      </div>
    </PublicShell>
  );
}
