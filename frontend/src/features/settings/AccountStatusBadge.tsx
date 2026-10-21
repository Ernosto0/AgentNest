import { useTranslation } from "react-i18next";
import { AlertIcon, CheckIcon, CriticalIcon } from "@/components/icons";

const TONES: Record<string, { box: string; Icon: typeof CheckIcon | null }> = {
  connected: {
    box: "bg-green-50 text-green-900 ring-green-500",
    Icon: CheckIcon,
  },
  degraded: {
    box: "bg-amber-50 text-amber-900 ring-amber-500",
    Icon: AlertIcon,
  },
  needs_reauth: {
    box: "bg-red-50 text-red-900 ring-red-400",
    Icon: CriticalIcon,
  },
  disconnected: {
    box: "bg-slate-100 text-slate-800 ring-slate-300",
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
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold ring-1 ring-inset ${tone.box}`}
    >
      {tone.Icon ? <tone.Icon className="text-base" /> : null}
      {t(`automation.accountStatus.${status}`, { defaultValue: status })}
    </span>
  );
}
