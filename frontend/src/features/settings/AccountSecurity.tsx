import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice } from "@/components/Feedback";
import { TextField } from "@/components/TextField";
import {
  useChangePassword,
  useRevokeAllSessions,
  useRevokeSession,
  useSessions,
} from "@/features/auth/hooks";

export function AccountSecurity() {
  const { t } = useTranslation();
  const sessions = useSessions();
  const revokeSession = useRevokeSession();
  const revokeAllSessions = useRevokeAllSessions();
  const changePassword = useChangePassword();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [clientError, setClientError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  const handleSubmitPassword = (e: FormEvent) => {
    e.preventDefault();
    setClientError(null);
    setPasswordSuccess(false);

    if (newPassword.length < 12) {
      setClientError(t("settings.passwordMinLength"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setClientError(t("settings.passwordMismatch"));
      return;
    }

    changePassword.mutate(
      { current_password: currentPassword, new_password: newPassword },
      {
        onSuccess: () => {
          setPasswordSuccess(true);
          setCurrentPassword("");
          setNewPassword("");
          setConfirmPassword("");
        },
      }
    );
  };

  const otherSessionsCount =
    sessions.data?.filter((s) => !s.is_current).length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Password Change Card */}
      <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <div>
          <h2 className="text-base font-heading font-semibold text-primary">
            {t("settings.changePassword")}
          </h2>
          <p className="mt-0.5 text-xs text-secondary leading-relaxed">
            {t("settings.passwordHint")}
          </p>
        </div>

        {passwordSuccess ? (
          <Notice tone="success" title={t("settings.passwordChanged")} />
        ) : null}

        {clientError ? (
          <p className="text-xs font-medium text-danger">{clientError}</p>
        ) : null}

        {changePassword.isError ? (
          <ErrorMessage error={changePassword.error} />
        ) : null}

        <form onSubmit={handleSubmitPassword} className="flex flex-col gap-3">
          <TextField
            label={t("settings.currentPassword")}
            type="password"
            autoComplete="current-password"
            required
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
          <TextField
            label={t("settings.newPassword")}
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <TextField
            label={t("settings.confirmPassword")}
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          <div className="pt-2">
            <Button
              type="submit"
              variant="primary"
              pending={changePassword.isPending}
              disabled={!currentPassword || !newPassword || !confirmPassword}
            >
              {t("settings.updatePassword")}
            </Button>
          </div>
        </form>
      </div>

      {/* Active Sessions Card */}
      <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-heading font-semibold text-primary">
              {t("settings.activeSessions")}
            </h2>
            <p className="mt-0.5 text-xs text-secondary leading-relaxed">
              {t("settings.sessionsHint")}
            </p>
          </div>
          {otherSessionsCount > 0 ? (
            <Button
              variant="secondary"
              pending={revokeAllSessions.isPending}
              onClick={() => revokeAllSessions.mutate(false)}
            >
              {t("settings.revokeOtherSessions")}
            </Button>
          ) : null}
        </div>

        {revokeSession.isError ? (
          <ErrorMessage error={revokeSession.error} />
        ) : null}
        {revokeAllSessions.isError ? (
          <ErrorMessage error={revokeAllSessions.error} />
        ) : null}

        <div className="flex flex-col divide-y divide-border">
          {sessions.data?.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
            >
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-primary">
                    {s.user_agent || t("settings.unknownDevice")}
                  </span>
                  {s.is_current ? (
                    <span className="rounded-full bg-success-subtle px-2 py-0.5 text-[10px] font-semibold text-success border border-border">
                      {t("settings.thisDevice")}
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center gap-2 text-xs text-secondary">
                  <span>{s.ip_address || "—"}</span>
                  <span>·</span>
                  <span>
                    {t("settings.lastActive")}:{" "}
                    {new Date(s.last_seen_at).toLocaleString()}
                  </span>
                </div>
              </div>
              {!s.is_current ? (
                <Button
                  variant="ghost"
                  className="text-danger hover:bg-danger-subtle"
                  pending={
                    revokeSession.isPending &&
                    revokeSession.variables === s.id
                  }
                  onClick={() => revokeSession.mutate(s.id)}
                >
                  {t("settings.revokeSession")}
                </Button>
              ) : null}
            </div>
          ))}
          {sessions.data?.length === 0 ? (
            <p className="py-2 text-xs text-secondary">
              {t("settings.noActiveSessions")}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
