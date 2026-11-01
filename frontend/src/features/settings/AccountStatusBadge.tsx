import { useTranslation } from "react-i18next";
import { AlertIcon, CheckIcon, CriticalIcon } from "@/components/icons";

const TONES: Record<string, { box: string; Icon: typeof CheckIcon | null }> = {
  connected: {
    box: "bg-success/10 text-success border-success/30",
    Icon: CheckIcon,
  },
  degraded: {
    box: "bg-warning/10 text-warning border-warning/30",
    Icon: AlertIcon,
  },
  needs_reauth: {
    box: "bg-danger/10 text-danger border-danger/30",
    Icon: CriticalIcon,
  },
  disconnected: {
    box: "bg-surface-subtle text-secondary border-border",
    Icon: null,
  },
};

/** The account status in the shared vocabulary (automation.accountStatus.*): the word, then the colour. */
export function AccountStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const tone = TONES[status] ?? TONES.disconnected!;
  return (
    <span
      data-testid="account-status-badge"
      data-status={status}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${tone.box}`}
    >
      {tone.Icon ? <tone.Icon className="text-sm" /> : null}
      {t(`automation.accountStatus.${status}`, { defaultValue: status })}
    </span>
  );
}
