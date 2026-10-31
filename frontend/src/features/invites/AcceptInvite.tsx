import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { AppError } from "@/api/errors";
import { PublicShell } from "@/app/layout/PublicShell";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice, Skeleton } from "@/components/Feedback";
import { TextField } from "@/components/TextField";
import { useLogout, useMe } from "@/features/auth/hooks";
import { useAcceptInvite } from "./hooks";

const LINK = "inline-flex min-h-11 items-center rounded-control font-medium text-action underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

/** No invite metadata endpoint exists. Workspace/role are not guessed before acceptance. */
export function AcceptInvite() {
  const { t } = useTranslation();
  const { token } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const me = useMe();
  const logout = useLogout();
  const accept = useAcceptInvite();
  const emailInput = useRef<HTMLInputElement>(null);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invalidEmail, setInvalidEmail] = useState(false);
  const emailTaken = accept.error instanceof AppError && accept.error.code === "CONFLICT_STATE" && accept.error.params.reason === "email_taken";
  const invalidInvite = !token || (accept.error instanceof AppError && accept.error.code === "INVITE_INVALID");
  const loginState = { from: { pathname: location.pathname, search: location.search, hash: location.hash } };
  function onSuccess(result: { workspace_id: string }) { navigate(`/w/${result.workspace_id}`, { replace: true }); }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || accept.isPending || !displayName.trim() || !email || !password) return;
    if (emailInput.current && !emailInput.current.validity.valid) { setInvalidEmail(true); emailInput.current.focus(); return; }
    setInvalidEmail(false);
    accept.mutate({ token, email, display_name: displayName, password }, { onSuccess });
  }
  return <PublicShell title={t("invite.title")} description={t("entry.inviteIntro")}>
    {me.isPending ? <Skeleton label={t("common.loading")} /> : me.isError ? <>
      <ErrorMessage error={me.error} /><Button variant="secondary" onClick={() => void me.refetch()}>{t("common.retry")}</Button>
    </> : logout.isError ? <>
      <ErrorMessage error={logout.error} />
      <Button variant="secondary" pending={me.isFetching} onClick={() => void me.refetch().then(result => {
        if (!result.isSuccess) return;
        logout.reset();
        if (result.data === null) navigate("/login", { state: loginState, replace: true });
      })}>{t("entry.checkAccount")}</Button>
    </> : <>
      {accept.isError && !emailTaken ? <ErrorMessage error={accept.error} /> : null}
      {invalidInvite ? <Link to={me.data ? "/" : "/login"} className={LINK}>{me.data ? t("wizard.back") : t("invite.signIn")}</Link> : me.data ? <section className="flex flex-col gap-5 rounded-panel border border-border bg-surface p-5 sm:p-6" aria-label={t("entry.inviteAccount")}>
        <div><p className="text-body text-secondary">{t("entry.signedInAs")}</p><p className="mt-1 text-form font-semibold break-words">{me.data.user.display_name}</p><p className="text-body break-all text-secondary">{me.data.user.email}</p></div>
        <p className="text-form text-secondary">{t("invite.joinHint")}</p>
        <Button block pending={accept.isPending} disabled={logout.isPending} onClick={() => { if (token && !accept.isPending) accept.mutate({ token }, { onSuccess }); }}>{accept.isPending ? t("invite.joining") : t("invite.join")}</Button>
        <Button variant="secondary" pending={logout.isPending} disabled={accept.isPending} onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login", { state: loginState, replace: true }) })}>{t("entry.useAnotherAccount")}</Button>
      </section> : <form onSubmit={submit} className="flex flex-col gap-5 rounded-panel border border-border bg-surface p-5 sm:p-6" noValidate aria-busy={accept.isPending}>
        <h2 className="type-section">{t("invite.newAccount")}</h2>
        <TextField label={t("invite.displayName")} name="display_name" autoComplete="name" required maxLength={100} value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        <TextField ref={emailInput} label={t("invite.email")} type="email" name="email" autoComplete="username" inputMode="email" autoCapitalize="none" spellCheck={false} required maxLength={320} value={email} error={invalidEmail ? t("entry.emailInvalid") : undefined} onChange={(event) => { setEmail(event.target.value); setInvalidEmail(false); }} />
        <TextField label={t("invite.password")} type="password" name="password" autoComplete="new-password" required maxLength={1000} value={password} onChange={(event) => setPassword(event.target.value)} />
        {emailTaken ? <div role="alert" data-testid="email-taken"><Notice tone="attention" title={t("invite.emailTaken")} /></div> : null}
        <Button type="submit" block pending={accept.isPending} disabled={!email || !password || !displayName.trim()} disabledReason={!email || !password || !displayName.trim() ? t("entry.inviteFieldsRequired") : undefined}>{accept.isPending ? t("invite.joining") : t("invite.submit")}</Button>
        <p className="text-body text-secondary">{t("entry.existingAccount")} <Link to="/login" state={loginState} className={LINK}>{t("invite.signIn")}</Link></p>
      </form>}
    </>}
  </PublicShell>;
}
