import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { TextField } from "@/components/TextField";
import { useLogin, useMe, useMeta } from "./hooks";

interface LocationState {
  from?: { pathname?: string; search?: string };
}

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const me = useMe();
  const meta = useMeta();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const from = (location.state as LocationState | null)?.from;
  const destination = from?.pathname ? `${from.pathname}${from.search ?? ""}` : "/";

  if (me.data) return <Navigate to={destination} replace />;

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate(
      { email, password },
      { onSuccess: () => navigate(destination, { replace: true }) },
    );
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 px-4 py-8">
      <div className="flex items-center justify-between gap-3">
        <span className="text-lg font-semibold text-indigo-800">
          {meta.data?.product_name ?? t("app.name")}
        </span>
        <LanguageSwitch />
      </div>
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{t("auth.title")}</h1>
        <p className="mt-1 text-slate-600">{t("auth.subtitle")}</p>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <TextField
          label={t("auth.email")}
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
          label={t("auth.password")}
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {login.isError ? <ErrorMessage error={login.error} /> : null}
        <Button type="submit" block disabled={login.isPending || !email || !password}>
          {login.isPending ? t("auth.submitting") : t("auth.submit")}
        </Button>
      </form>
    </main>
  );
}
