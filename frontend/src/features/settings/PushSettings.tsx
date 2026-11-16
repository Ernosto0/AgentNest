import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChoiceField } from "@/components/FormFields";
import { useMe } from "@/features/auth/hooks";
import { IosInstallGuide } from "@/features/notifications/PushPrompt";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import {
  PUSH_CATEGORIES,
  useEnablePush,
  usePushConfig,
  usePushDevices,
  usePushPreferences,
  useRemovePushDevice,
  useSavePushPreferences,
} from "@/pwa/hooks";
import { needsHomeScreenInstall, pushPermission, pushSupported, storedDeviceId } from "@/pwa/push";
import { useLocalTime } from "./hooks";

/**
 * Phone notifications, next to the Telegram connection: which kinds of event may notify this
 * user (per category, off until switched on) and which devices are registered. Renders nothing
 * until the server says push is configured, so a deployment without VAPID keys shows no push UI.
 */
export function PushSettings() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const me = useMe();
  const userId = me.data?.user.id ?? "";
  const config = usePushConfig(workspace.id);
  const enabled = config.data?.enabled === true;
  const preferences = usePushPreferences(workspace.id, enabled);
  const devices = usePushDevices(workspace.id, enabled);
  const save = useSavePushPreferences(workspace.id);
  const enable = useEnablePush(workspace.id);
  const remove = useRemovePushDevice(workspace.id);
  const formatTime = useLocalTime();

  if (!enabled) return null;

  const ios = needsHomeScreenInstall();
  const supported = pushSupported();
  const denied = supported && pushPermission() === "denied";
  const thisDevice = userId ? storedDeviceId(userId, workspace.id) : null;
  const thisDeviceOn = thisDevice !== null && (devices.data ?? []).some((d) => d.id === thisDevice);
  const outcome = enable.data && enable.data.status !== "subscribed" ? enable.data.status : null;

  return (
    <div
      data-testid="push-settings"
      className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs"
    >
      <div>
        <h2 className="text-base font-heading font-semibold text-primary">{t("push.settings.title")}</h2>
        <p className="mt-1 text-sm text-secondary">{t("push.settings.intro")}</p>
      </div>

      <div className="flex flex-col gap-3 rounded-control border border-border/60 bg-surface-subtle p-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-secondary">
          {t("push.settings.deviceTitle")}
        </p>
        {ios ? (
          <IosInstallGuide />
        ) : !supported ? (
          <p className="text-body text-secondary">{t("push.settings.unsupported")}</p>
        ) : denied ? (
          <p role="alert" className="text-body text-danger">
            {t("push.settings.denied")}
          </p>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p data-testid="push-device-state" className="text-body text-primary">
              {thisDeviceOn ? t("push.settings.deviceOn") : t("push.settings.deviceOff")}
            </p>
            {thisDeviceOn && thisDevice ? (
              <Button
                variant="secondary"
                disabled={remove.isPending}
                onClick={() => remove.mutate(thisDevice)}
              >
                {remove.isPending ? t("push.settings.working") : t("push.settings.disable")}
              </Button>
            ) : (
              <Button disabled={enable.isPending} onClick={() => enable.mutate()}>
                {enable.isPending ? t("push.settings.working") : t("push.settings.enable")}
              </Button>
            )}
          </div>
        )}
        {outcome ? (
          <p role="alert" className="text-body text-danger">
            {t(`push.outcome.${outcome}`)}
          </p>
        ) : null}
      </div>

      <fieldset className="flex min-w-0 flex-col gap-1" disabled={preferences.isPending || save.isPending}>
        <legend className="text-xs font-semibold uppercase tracking-wider text-secondary">
          {t("push.settings.typesTitle")}
        </legend>
        {PUSH_CATEGORIES.map((category) => (
          <ChoiceField
            key={category}
            label={t(`push.settings.types.${category}.label`)}
            hint={t(`push.settings.types.${category}.hint`)}
            checked={preferences.data?.[category] ?? false}
            onChange={(event) => save.mutate({ [category]: event.target.checked })}
          />
        ))}
        <p className="mt-1 text-metadata text-secondary">{t("push.settings.quiet")}</p>
      </fieldset>

      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-secondary">
          {t("push.settings.devicesTitle")}
        </p>
        {devices.data && devices.data.length === 0 ? (
          <p className="text-body text-secondary">{t("push.settings.devicesNone")}</p>
        ) : null}
        <ul className="divide-y divide-border">
          {(devices.data ?? []).map((device) => (
            <li key={device.id} className="flex min-w-0 flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <p className="text-body font-medium text-primary">{device.label}</p>
                <p className="text-metadata text-secondary">
                  {device.last_success_at
                    ? t("push.settings.lastSent", { time: formatTime(device.last_success_at) })
                    : t("push.settings.neverSent")}
                </p>
              </div>
              <Button
                variant="ghost"
                disabled={remove.isPending}
                aria-label={`${t("push.settings.remove")}: ${device.label}`}
                onClick={() => remove.mutate(device.id)}
              >
                {t("push.settings.remove")}
              </Button>
            </li>
          ))}
        </ul>
      </div>

      {preferences.error ? <ErrorMessage error={preferences.error} /> : null}
      {save.error ? <ErrorMessage error={save.error} /> : null}
      {enable.error ? <ErrorMessage error={enable.error} /> : null}
      {remove.error ? <ErrorMessage error={remove.error} /> : null}
    </div>
  );
}
