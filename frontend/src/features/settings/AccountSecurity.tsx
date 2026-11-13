import { useEffect, useRef, useState, type FormEvent, type InputHTMLAttributes } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AppError } from "@/api/errors";
import type { AuthSession } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice, Skeleton } from "@/components/Feedback";
import { Field } from "@/components/Field";
import { FIELD_CONTROL, useFieldIds } from "@/components/fieldIds";
import { CheckIcon, EyeIcon, EyeOffIcon, KeyIcon, LockIcon, MonitorIcon, SmartphoneIcon, TabletIcon } from "@/components/icons";
import { absoluteTime, relativeTime } from "@/features/agent/presentation";
import { useChangePassword, useRevokeAllSessions, useRevokeSession, useSessions } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { describeUserAgent, type DeviceInfo } from "./deviceLabel";
import { FOCUS, PanelTitle, SettingsPanel, SettingsSection } from "./SettingsParts";

const MIN_PASSWORD = 12; // app.core.security.MIN_PASSWORD_LENGTH
// Sessions record activity at most every five minutes (identity SESSION_TOUCH_INTERVAL).
const RECENT_MS = 10 * 60_000;

export function SecuritySection() {
  const { t } = useTranslation();
  return (
    <SettingsSection id="security" title={t("settings.nav.security")} description={t("settings.security.description")}>
      <PasswordPanel />
      <SessionsPanel />
    </SettingsSection>
  );
}

/** Password input with an accessible show/hide toggle. The value never leaves the form state. */
function PasswordField({
  label,
  hint,
  error,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label: string; hint?: string; error?: string }) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const ids = useFieldIds(undefined, undefined, hint, error);
  return (
    <Field label={label} hint={hint} error={error} {...ids}>
      <div className="relative min-w-0">
        <input
          {...props}
          id={ids.id}
          type={visible ? "text" : "password"}
          spellCheck={false}
          autoCapitalize="off"
          aria-invalid={error ? true : undefined}
          aria-describedby={ids.describedBy}
          className={`${FIELD_CONTROL} min-h-11 pr-12`}
        />
        <button
          type="button"
          onClick={() => setVisible((value) => !value)}
          aria-pressed={visible}
          aria-controls={ids.id}
          aria-label={visible ? t("settings.security.hidePassword") : t("settings.security.showPassword")}
          className={`absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-control text-lg text-secondary hover:text-primary ${FOCUS} focus-visible:-outline-offset-2`}
        >
          {visible ? <EyeOffIcon aria-hidden="true" /> : <EyeIcon aria-hidden="true" />}
        </button>
      </div>
    </Field>
  );
}

type PasswordErrors = { current?: string; next?: string; confirm?: string };

function PasswordPanel() {
  const { t } = useTranslation();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<PasswordErrors>({});
  const [done, setDone] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  const focusFirstInvalid = () =>
    requestAnimationFrame(() => formRef.current?.querySelector<HTMLInputElement>("input[aria-invalid='true']")?.focus());

  /** Map the server's answer onto the field it concerns; anything else stays a general error. */
  const serverErrors = (error: AppError): PasswordErrors | null => {
    if (error.code === "INVALID_CREDENTIALS") return { current: t("settings.security.currentWrong") };
    if (error.code === "VALIDATION_FAILED") {
      const codes = error.fieldErrors.filter((e) => e.field === "new_password").map((e) => e.code);
      if (codes.includes("too_common")) return { next: t("settings.security.tooCommon") };
      if (codes.includes("too_short") || codes.includes("string_too_short")) return { next: t("settings.security.tooShort") };
    }
    return null;
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setDone(false);
    const found: PasswordErrors = {};
    if (!current) found.current = t("settings.security.currentRequired");
    if (next.length < MIN_PASSWORD) found.next = t("settings.security.tooShort");
    else if (next === current) found.next = t("settings.security.sameAsCurrent");
    if (confirm !== next) found.confirm = t("settings.security.mismatch");
    setErrors(found);
    if (Object.keys(found).length) return focusFirstInvalid();

    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setDone(true);
          setCurrent("");
          setNext("");
          setConfirm("");
        },
        onError: (error) => {
          const mapped = serverErrors(error);
          if (mapped) {
            setErrors(mapped);
            focusFirstInvalid();
          }
        },
      },
    );
  };

  const generalError = change.isError && !serverErrors(change.error) ? change.error : null;
  const clear = (field: keyof PasswordErrors) => setErrors((value) => ({ ...value, [field]: undefined }));

  return (
    <SettingsPanel as="section" aria-labelledby="settings-password-title">
      <PanelTitle id="settings-password-title" icon={<KeyIcon />} title={t("settings.security.passwordTitle")} description={t("settings.security.passwordHint")} />
      <form ref={formRef} onSubmit={submit} noValidate className="flex min-w-0 flex-col gap-4 border-t border-border/70 px-4 py-4 sm:px-5 sm:pb-5">
        {done ? (
          <Notice tone="success" title={t("settings.security.passwordChanged")} live="polite">
            {t("settings.security.passwordChangedBody")}
          </Notice>
        ) : null}
        <div className="grid min-w-0 gap-4 md:max-w-md">
          <PasswordField
            label={t("settings.security.current")}
            autoComplete="current-password"
            value={current}
            error={errors.current}
            onChange={(event) => {
              setCurrent(event.target.value);
              clear("current");
            }}
          />
          <PasswordField
            label={t("settings.security.new")}
            autoComplete="new-password"
            hint={t("settings.security.newHint", { min: MIN_PASSWORD })}
            value={next}
            error={errors.next}
            onChange={(event) => {
              setNext(event.target.value);
              clear("next");
            }}
          />
          <PasswordField
            label={t("settings.security.confirm")}
            autoComplete="new-password"
            value={confirm}
            error={errors.confirm}
            onChange={(event) => {
              setConfirm(event.target.value);
              clear("confirm");
            }}
          />
        </div>
        {generalError ? <ErrorMessage error={generalError} /> : null}
        <p className="flex items-start gap-2 text-metadata text-secondary">
          <LockIcon aria-hidden="true" className="mt-0.5 shrink-0" />
          {t("settings.security.signsOutOthers")}
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Button type="submit" pending={change.isPending} disabled={!current || !next || !confirm}>
            {t("settings.security.update")}
          </Button>
          <Link to="/reset-password" className={`inline-flex min-h-11 items-center rounded-control px-1 text-body font-medium text-action underline-offset-2 hover:underline ${FOCUS}`}>
            {t("settings.security.forgot")}
          </Link>
        </div>
      </form>
    </SettingsPanel>
  );
}

function deviceName(device: DeviceInfo, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (device.browser && device.os) return t("settings.sessions.browserOnOs", { browser: device.browser, os: device.os });
  if (device.browser) return device.browser;
  if (device.os) return t("settings.sessions.osDevice", { os: device.os });
  return t("settings.sessions.unknownDevice");
}

function DeviceIcon({ kind }: { kind: DeviceInfo["kind"] }) {
  const Icon = kind === "phone" ? SmartphoneIcon : kind === "tablet" ? TabletIcon : MonitorIcon;
  return <Icon aria-hidden="true" />;
}

type Confirm = { kind: "one"; session: AuthSession; name: string } | { kind: "others"; count: number };

function SessionsPanel() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const sessions = useSessions();
  const revokeOne = useRevokeSession();
  const revokeOthers = useRevokeAllSessions();
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const othersButton = useRef<HTMLButtonElement>(null);
  const dialogCancel = useRef<HTMLButtonElement>(null);
  // "Active recently" / "2 hours ago" stay true while the page is open.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const list = [...(sessions.data ?? [])].sort((a, b) => Number(b.is_current) - Number(a.is_current));
  const others = list.filter((s) => !s.is_current);
  const pending = revokeOne.isPending || revokeOthers.isPending;
  const failure = revokeOne.error ?? revokeOthers.error;

  const close = () => {
    if (!pending) setConfirm(null);
  };
  const run = () => {
    if (!confirm) return;
    setResult(null);
    if (confirm.kind === "one") {
      revokeOne.mutate(confirm.session.id, {
        onSuccess: () => setResult(t("settings.sessions.signedOutOne", { device: confirm.name })),
        // Already ended elsewhere (expired or revoked): the refreshed list shows the truth.
        onError: (error) => {
          if (error.code === "NOT_FOUND") setResult(t("settings.sessions.alreadyEnded"));
        },
        onSettled: () => setConfirm(null),
      });
    } else {
      revokeOthers.mutate(false, {
        onSuccess: () => setResult(t("settings.sessions.signedOutOthers")),
        onSettled: () => setConfirm(null),
      });
    }
  };

  return (
    <SettingsPanel as="section" aria-labelledby="settings-sessions-title">
      <PanelTitle
        id="settings-sessions-title"
        icon={<MonitorIcon />}
        title={t("settings.sessions.title")}
        description={t("settings.sessions.description")}
        action={
          others.length > 0 ? (
            <Button
              ref={othersButton}
              variant="secondary"
              className="text-danger sm:min-h-10"
              onClick={() => {
                revokeOne.reset();
                revokeOthers.reset();
                setConfirm({ kind: "others", count: others.length });
              }}
            >
              {t("settings.sessions.signOutOthers")}
            </Button>
          ) : undefined
        }
      />

      {result ? (
        <p role="status" className="mx-4 mb-3 flex items-center gap-2 rounded-control bg-success-subtle px-3 py-2 text-body font-medium text-success sm:mx-5">
          <CheckIcon aria-hidden="true" className="shrink-0" />
          {result}
        </p>
      ) : null}
      {failure && failure.code !== "NOT_FOUND" ? (
        <div className="mx-4 mb-3 sm:mx-5">
          <ErrorMessage error={failure} />
        </div>
      ) : null}

      {sessions.isPending ? (
        <div className="border-t border-border/70 px-4 py-4 sm:px-5">
          <Skeleton label={t("common.loading")} rows={2} />
        </div>
      ) : sessions.isError ? (
        <div className="border-t border-border/70 px-4 py-4 sm:px-5">
          <ErrorMessage error={sessions.error} />
        </div>
      ) : (
        <ul aria-label={t("settings.sessions.title")}>
          {list.map((session) => {
            const device = describeUserAgent(session.user_agent);
            const name = deviceName(device, t);
            const lastSeen = new Date(session.last_seen_at).getTime();
            const recent = session.is_current || now - lastSeen < RECENT_MS;
            return (
              <li
                key={session.id}
                data-testid="session-row"
                data-current={session.is_current || undefined}
                className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 border-t border-border/70 px-4 py-3.5 sm:flex-nowrap sm:px-5"
              >
                <span
                  aria-hidden="true"
                  className={`flex size-10 shrink-0 items-center justify-center rounded-xl text-lg ${
                    session.is_current ? "bg-assistant text-action" : "bg-surface-subtle text-secondary"
                  }`}
                >
                  <DeviceIcon kind={device.kind} />
                </span>
                <div className="min-w-0 flex-1 basis-48">
                  <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="text-body font-semibold text-primary [overflow-wrap:anywhere]">{name}</span>
                    {session.is_current ? (
                      <span className="inline-flex items-center rounded-full bg-success-subtle px-2 text-[11px] leading-5 font-semibold text-success">
                        {t("settings.sessions.thisDevice")}
                      </span>
                    ) : null}
                  </p>
                  <p className="text-metadata text-secondary">
                    <span>{t(`settings.sessions.kind.${device.kind}`)}</span>
                    <span aria-hidden="true"> · </span>
                    {session.is_current ? (
                      <span className="font-medium text-success">{t("settings.sessions.activeNow")}</span>
                    ) : (
                      <time dateTime={session.last_seen_at} title={absoluteTime(session.last_seen_at, i18n.language, workspace.timezone)}>
                        {recent
                          ? t("settings.sessions.activeRecently")
                          : t("settings.sessions.lastActive", { when: relativeTime(session.last_seen_at, i18n.language, now) })}
                      </time>
                    )}
                  </p>
                  <p className="text-metadata text-secondary [overflow-wrap:anywhere]">
                    {t("settings.sessions.signedIn", {
                      date: new Date(session.created_at).toLocaleDateString(i18n.language, { dateStyle: "medium", timeZone: workspace.timezone }),
                    })}
                    {session.ip_address ? (
                      <>
                        <span aria-hidden="true"> · </span>
                        {t("settings.sessions.ip", { ip: session.ip_address })}
                      </>
                    ) : null}
                  </p>
                </div>
                {!session.is_current ? (
                  <Button
                    variant="ghost"
                    className="ml-[3.25rem] text-danger enabled:hover:bg-danger-subtle sm:ml-0 sm:min-h-10"
                    aria-label={t("settings.sessions.signOutDevice", { device: name })}
                    onClick={() => {
                      revokeOne.reset();
                      revokeOthers.reset();
                      setConfirm({ kind: "one", session, name });
                    }}
                  >
                    {t("settings.sessions.signOut")}
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {sessions.isSuccess ? (
        <p className="border-t border-border/70 px-4 py-3 text-metadata text-secondary sm:px-5">
          {others.length === 0 ? t("settings.sessions.onlyThis") : t("settings.sessions.unrecognised")}
        </p>
      ) : null}

      {confirm ? (
        <BottomSheet
          title={
            confirm.kind === "one"
              ? t("settings.sessions.confirmOneTitle", { device: confirm.name })
              : t("settings.sessions.confirmOthersTitle")
          }
          onClose={close}
          dismissible={!pending}
          initialFocusRef={dialogCancel}
          returnFocusRef={confirm.kind === "others" ? othersButton : undefined}
          footer={
            <div className="flex flex-wrap gap-2">
              <Button variant="danger" pending={pending} onClick={run}>
                {confirm.kind === "one" ? t("settings.sessions.signOut") : t("settings.sessions.confirmOthersAction")}
              </Button>
              <Button ref={dialogCancel} variant="secondary" disabled={pending} onClick={close}>
                {t("common.cancel")}
              </Button>
            </div>
          }
        >
          <p className="text-body text-secondary">
            {confirm.kind === "one"
              ? t("settings.sessions.confirmOneBody")
              : t("settings.sessions.confirmOthersBody", { count: confirm.count })}
          </p>
        </BottomSheet>
      ) : null}
    </SettingsPanel>
  );
}
