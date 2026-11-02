import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PublicShell } from "@/app/layout/PublicShell";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice } from "@/components/Feedback";
import { TextField } from "@/components/TextField";
import { useConfirmPasswordReset, useRequestPasswordReset } from "./hooks";

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { token } = useParams<{ token?: string }>();
  const requestReset = useRequestPasswordReset();
  const confirmReset = useConfirmPasswordReset();

  // Request state
  const emailInput = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [invalidEmail, setInvalidEmail] = useState(false);
  const [requestSent, setRequestSent] = useState(false);

  // Confirm state
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordMismatch, setPasswordMismatch] = useState(false);
  const [resetCompleted, setResetCompleted] = useState(false);

  function handleRequestSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (requestReset.isPending || !email.trim()) return;
    if (emailInput.current && !emailInput.current.validity.valid) {
      setInvalidEmail(true);
      emailInput.current.focus();
      return;
    }
    setInvalidEmail(false);
    requestReset.mutate(
      { email: email.trim() },
      {
        onSuccess: () => setRequestSent(true),
      }
    );
  }

  function handleConfirmSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (confirmReset.isPending || !token || !newPassword) return;
    if (newPassword !== confirmPassword) {
      setPasswordMismatch(true);
      return;
    }
    setPasswordMismatch(false);
    confirmReset.mutate(
      { token, new_password: newPassword },
      {
        onSuccess: () => setResetCompleted(true),
      }
    );
  }

  if (token) {
    return (
      <PublicShell
        title={t("auth.setNewPasswordTitle")}
        description={t("auth.setNewPasswordSubtitle")}
      >
        {resetCompleted ? (
          <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 sm:p-6">
            <Notice
              tone="success"
              title={t("auth.passwordResetSuccessTitle")}
            >
              <p>{t("auth.passwordResetSuccessDesc")}</p>
            </Notice>
            <Button onClick={() => navigate("/login")}>{t("auth.goToLogin")}</Button>
          </div>
        ) : (
          <form
            onSubmit={handleConfirmSubmit}
            className="flex flex-col gap-5 rounded-panel border border-border bg-surface p-5 sm:p-6"
            noValidate
            aria-busy={confirmReset.isPending}
          >
            <div>
              <TextField
                label={t("auth.newPassword")}
                type="password"
                name="new_password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={1000}
                value={newPassword}
                onChange={(e) => {
                  setNewPassword(e.target.value);
                  setPasswordMismatch(false);
                }}
              />
              <p className="mt-1 text-xs text-secondary">{t("auth.passwordMinLengthHint")}</p>
            </div>
            <TextField
              label={t("auth.confirmNewPassword")}
              type="password"
              name="confirm_password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={1000}
              value={confirmPassword}
              error={passwordMismatch ? t("auth.passwordsDoNotMatch") : undefined}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                setPasswordMismatch(false);
              }}
            />
            {confirmReset.isError ? <ErrorMessage error={confirmReset.error} /> : null}
            <Button
              type="submit"
              block
              pending={confirmReset.isPending}
              disabled={newPassword.length < 12 || !confirmPassword}
            >
              {confirmReset.isPending ? t("auth.submitting") : t("auth.submitNewPassword")}
            </Button>
            <div className="text-center">
              <Link to="/login" className="text-xs text-secondary hover:underline">
                {t("auth.backToLogin")}
              </Link>
            </div>
          </form>
        )}
      </PublicShell>
    );
  }

  return (
    <PublicShell
      title={t("auth.resetPasswordTitle")}
      description={t("auth.resetPasswordSubtitle")}
    >
      {requestSent ? (
        <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 sm:p-6">
          <Notice
            tone="success"
            title={t("auth.resetEmailSentTitle")}
          >
            <p>{t("auth.resetEmailSentDesc")}</p>
          </Notice>
          <Button variant="secondary" onClick={() => navigate("/login")}>
            {t("auth.backToLogin")}
          </Button>
        </div>
      ) : (
        <form
          onSubmit={handleRequestSubmit}
          className="flex flex-col gap-5 rounded-panel border border-border bg-surface p-5 sm:p-6"
          noValidate
          aria-busy={requestReset.isPending}
        >
          <TextField
            ref={emailInput}
            label={t("auth.email")}
            type="email"
            name="email"
            autoComplete="username"
            inputMode="email"
            autoCapitalize="none"
            spellCheck={false}
            required
            maxLength={320}
            value={email}
            error={invalidEmail ? t("entry.emailInvalid") : undefined}
            onChange={(e) => {
              setEmail(e.target.value);
              setInvalidEmail(false);
            }}
          />
          {requestReset.isError ? <ErrorMessage error={requestReset.error} /> : null}
          <Button
            type="submit"
            block
            pending={requestReset.isPending}
            disabled={!email.trim()}
          >
            {requestReset.isPending ? t("auth.submitting") : t("auth.sendResetLink")}
          </Button>
          <div className="text-center">
            <Link to="/login" className="text-xs text-secondary hover:underline">
              {t("auth.backToLogin")}
            </Link>
          </div>
        </form>
      )}
    </PublicShell>
  );
}
