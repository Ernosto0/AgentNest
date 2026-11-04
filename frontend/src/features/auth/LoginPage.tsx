import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { PublicShell } from "@/app/layout/PublicShell";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice, Skeleton } from "@/components/Feedback";
import { TextField } from "@/components/TextField";
import { useLogin, useMe } from "./hooks";
import { returnDestination, type LoginLocationState } from "./returnTo";

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const me = useMe();
  const login = useLogin();
  const emailInput = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invalidEmail, setInvalidEmail] = useState(false);
  const from = (location.state as LoginLocationState | null)?.from;
  const destination = returnDestination(from);
  if (me.data) return <Navigate to={destination} replace />;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (login.isPending || !email || !password) return;
    if (emailInput.current && !emailInput.current.validity.valid) {
      setInvalidEmail(true); emailInput.current.focus(); return;
    }
    setInvalidEmail(false);
    login.mutate({ email, password }, { onSuccess: () => navigate(destination, { replace: true }) });
  }
  return <PublicShell title={t("auth.title")} description={t("auth.subtitle")}>
    {me.isPending ? <Skeleton label={t("common.loading")} /> : me.isError ? <>
      <ErrorMessage error={me.error} /><Button variant="secondary" onClick={() => void me.refetch()}>{t("common.retry")}</Button>
    </> : <>
      {from ? <Notice title={t("entry.signInToContinue")} /> : null}
      <form onSubmit={submit} className="flex flex-col gap-5 rounded-2xl border border-border/80 bg-surface p-6 sm:p-8 shadow-card-modern" noValidate aria-busy={login.isPending}>
        <TextField ref={emailInput} label={t("auth.email")} type="email" name="email" autoComplete="username" inputMode="email" autoCapitalize="none" spellCheck={false} required maxLength={320} value={email} error={invalidEmail ? t("entry.emailInvalid") : undefined} onChange={(event) => { setEmail(event.target.value); setInvalidEmail(false); }} />
        <div className="flex flex-col gap-1.5">
          <TextField label={t("auth.password")} type="password" name="password" autoComplete="current-password" required maxLength={1000} value={password} onChange={(event) => setPassword(event.target.value)} />
          <div className="text-right">
            <Link to="/reset-password" className="text-xs text-secondary hover:underline">
              {t("auth.forgotPassword")}
            </Link>
          </div>
        </div>
        {login.isError ? <ErrorMessage error={login.error} /> : null}
        <Button type="submit" block pending={login.isPending} disabled={!email || !password} disabledReason={!email || !password ? t("entry.credentialsRequired") : undefined}>{login.isPending ? t("auth.submitting") : t("auth.submit")}</Button>
      </form>
      <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-secondary">
        <Link to="/privacy" className="hover:underline">
          {t("legal.privacyTitle")}
        </Link>
        <span>•</span>
        <Link to="/data-deletion" className="hover:underline">
          {t("legal.dataDeletionTitle")}
        </Link>
      </div>
    </>}
  </PublicShell>;
}
