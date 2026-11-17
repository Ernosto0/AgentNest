import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "@/api/client";
import { PublicShell } from "@/app/layout/PublicShell";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice, Skeleton } from "@/components/Feedback";
import { TextField } from "@/components/TextField";
import { meKey, useLogout, useMe, useMeta } from "./hooks";

const panel = "flex flex-col gap-5 rounded-panel border border-border bg-surface p-5 sm:p-6";
const linkStyle = "inline-flex min-h-11 items-center text-action hover:underline focus-visible:outline-2 focus-visible:outline-focus";

export function SignupPage() {
  const { t, i18n } = useTranslation();
  const meta = useMeta();
  const me = useMe();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const register = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/register", { body: {
      email, password, name, accepted_terms_version: meta.data!.terms_version,
      ui_locale: i18n.language === "en" ? "en" : "tr",
    } })),
    onSuccess: () => navigate("/check-email", { replace: true, state: { email } }),
  });
  if (me.data) return <Navigate to={me.data.user.email_verified ? "/" : "/check-email"} replace />;
  if (meta.data && !meta.data.signup_enabled) return <Navigate to="/login" replace />;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (accepted && meta.data?.signup_enabled && !register.isPending) register.mutate();
  }
  return <PublicShell title={t("signup.title")} description={t("signup.subtitle")}>
    {meta.isPending ? <Skeleton label={t("common.loading")} /> : meta.isError ? <><ErrorMessage error={meta.error} /><Button onClick={() => void meta.refetch()}>{t("common.retry")}</Button></> : <form onSubmit={submit} className={panel} aria-busy={register.isPending}>
      <TextField label={t("signup.name")} autoComplete="name" required maxLength={100} value={name} onChange={e => setName(e.target.value)} />
      <TextField label={t("auth.email")} type="email" autoComplete="email" autoCapitalize="none" spellCheck={false} required maxLength={320} value={email} onChange={e => setEmail(e.target.value)} />
      <TextField label={t("auth.password")} type="password" autoComplete="new-password" required minLength={10} maxLength={1000} hint={t("signup.passwordHint")} value={password} onChange={e => setPassword(e.target.value)} />
      <div><label className="flex min-h-11 items-start gap-3"><input type="checkbox" required checked={accepted} onChange={e => setAccepted(e.target.checked)} className="mt-1 size-5 shrink-0 accent-action" /><span>{t("signup.accept")}</span></label>
        <div className="flex flex-wrap gap-4"><Link className={linkStyle} to="/terms" target="_blank" rel="noopener">{t("signup.terms")}</Link><Link className={linkStyle} to="/privacy" target="_blank" rel="noopener">{t("legal.privacyTitle")}</Link></div>
      </div>
      {register.isError ? <ErrorMessage error={register.error} /> : null}
      <Button type="submit" block pending={register.isPending} disabled={!accepted || !name.trim() || !email || password.length < 10}>{t("signup.title")}</Button>
    </form>}
    <Link className={linkStyle} to="/login">{t("legal.backToLogin")}</Link>
  </PublicShell>;
}

export function CheckEmailPage() {
  const { t } = useTranslation();
  const meta = useMeta();
  const me = useMe();
  const logout = useLogout();
  const location = useLocation();
  const [email, setEmail] = useState((location.state as { email?: string } | null)?.email ?? "");
  const resend = useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/auth/resend-verification", { body: { email: me.data?.user.email ?? email } })) });
  if (me.data?.user.email_verified) return <Navigate to="/workspaces/new" replace />;
  return <PublicShell title={t("signup.checkTitle")} description={t("signup.checkBody")}>
    {me.isError ? <ErrorMessage error={me.error} /> : null}
    {meta.isError ? <><ErrorMessage error={meta.error} /><Button onClick={() => void meta.refetch()}>{t("common.retry")}</Button></> : null}
    {meta.data?.signup_enabled ? <form className={panel} onSubmit={e => { e.preventDefault(); if (!resend.isPending) resend.mutate(); }}>
      <TextField label={t("auth.email")} type="email" autoComplete="email" required maxLength={320} value={me.data?.user.email ?? email} readOnly={Boolean(me.data)} onChange={e => setEmail(e.target.value)} />
      {resend.isError ? <ErrorMessage error={resend.error} /> : null}
      {resend.isSuccess ? <Notice title={t("signup.resent")} /> : null}
      <Button type="submit" pending={resend.isPending}>{t("signup.resend")}</Button>
    </form> : meta.data ? <Notice title={t("signup.closed")} /> : null}
    {me.data ? <><Button variant="secondary" onClick={() => void me.refetch()}>{t("signup.refresh")}</Button><Button variant="ghost" pending={logout.isPending} onClick={() => logout.mutate()}>{t("signup.logout")}</Button></> : <Link className={linkStyle} to="/login" state={{ from: { pathname: "/workspaces/new" } }}>{t("legal.backToLogin")}</Link>}
  </PublicShell>;
}

export function VerifyEmailPage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const me = useMe();
  const queryClient = useQueryClient();
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/verify-email", { body: { token } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meKey }),
  });
  if (verify.isSuccess && me.data?.user.email_verified) return <Navigate to="/workspaces/new" replace />;
  return <PublicShell title={t("signup.verifyTitle")} description={t("signup.verifyBody")}>
    <div className={panel}>
      {verify.isSuccess ? <><Notice title={t("signup.verified")} /><Link className={linkStyle} to="/login" state={{ from: { pathname: "/workspaces/new" } }} replace>{t("signup.continue")}</Link></> : <>
        {verify.isError ? <><ErrorMessage error={verify.error} /><Link className={linkStyle} to="/check-email">{t("signup.resend")}</Link></> : null}
        <Button pending={verify.isPending} onClick={() => verify.mutate()}>{t("signup.verify")}</Button>
      </>}
    </div>
  </PublicShell>;
}
