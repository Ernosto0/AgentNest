import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AppError } from "@/api/errors";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { FullScreenStatus } from "@/components/FullScreenStatus";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { TextField } from "@/components/TextField";
import { useMe, useMeta } from "@/features/auth/hooks";
import { useAcceptInvite } from "./hooks";

/** The public invite page: join when signed in, or create an account and join. */
export function AcceptInvite() {
  const { t } = useTranslation();
  const { token } = useParams();
  const navigate = useNavigate();
  const me = useMe();
  const meta = useMeta();
  const accept = useAcceptInvite();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  if (me.isPending || !token) return <FullScreenStatus>{t("common.loading")}</FullScreenStatus>;

  const signedIn = me.data !== null;
  const emailTaken =
    accept.error instanceof AppError &&
    accept.error.code === "CONFLICT_STATE" &&
    accept.error.params.reason === "email_taken";

  function onSuccess(result: { workspace_id: string }) {
    navigate(`/w/${result.workspace_id}`, { replace: true });
  }

  const join = () => accept.mutate({ token }, { onSuccess });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    accept.mutate({ token, email, display_name: displayName, password }, { onSuccess });
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 px-4 py-8">
      <div className="flex items-center justify-between gap-3">
        <span className="text-lg font-semibold text-indigo-800">
          {meta.data?.product_name ?? t("app.name")}
        </span>
        <LanguageSwitch />
      </div>

      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{t("invite.title")}</h1>
      </div>

      {accept.isError && !emailTaken ? <ErrorMessage error={accept.error} /> : null}

      {signedIn ? (
        <div className="flex flex-col gap-4">
          <p className="text-slate-600">{t("invite.joinHint")}</p>
          <Button type="button" block disabled={accept.isPending} onClick={join}>
            {accept.isPending ? t("invite.joining") : t("invite.join")}
          </Button>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <h2 className="text-lg font-semibold text-slate-900">{t("invite.newAccount")}</h2>
          <TextField
            label={t("invite.displayName")}
            name="display_name"
            autoComplete="name"
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
          <TextField
            label={t("invite.email")}
            type="email"
            name="email"
            autoComplete="username"
            inputMode="email"
            autoCapitalize="none"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <TextField
            label={t("invite.password")}
            type="password"
            name="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {emailTaken ? (
            <p role="alert" data-testid="email-taken" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-300">
              {t("invite.emailTaken")}{" "}
              <Link to="/login" className="font-semibold underline underline-offset-2">
                {t("invite.signIn")}
              </Link>
            </p>
          ) : null}
          <Button type="submit" block disabled={accept.isPending || !email || !password || !displayName}>
            {accept.isPending ? t("invite.joining") : t("invite.submit")}
          </Button>
        </form>
      )}
    </main>
  );
}
