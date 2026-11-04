import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import QRCode from "qrcode";
import type { Invite, Member, Role } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useMe } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import {
  useChangeMemberRole,
  useCreateInvite,
  useMembers,
  usePendingInvites,
  useRemoveMember,
  useRevokeInvite,
} from "./hooks";

const ROLES: Role[] = ["owner", "manager", "staff"];

/** The invite link as a QR code (rendered as an SVG data URL, so it needs no canvas). */
function InviteQr({ value }: { value: string }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let cancelled = false;
    QRCode.toString(value, { type: "svg", width: 256, margin: 1 })
      .then((svg) => {
        if (!cancelled) setSrc(`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [value]);

  if (!src) {
    return <div data-testid="invite-qr" aria-hidden="true" className="mx-auto h-44 w-44" />;
  }
  return <img data-testid="invite-qr" src={src} alt="" aria-hidden="true" className="mx-auto h-44 w-44" />;
}

/** The members list, the role/remove controls, and the invite sheet (owner). */
export function Members() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const me = useMe();
  const owner = role === "owner";
  const members = useMembers(workspace.id);
  const invites = usePendingInvites(workspace.id);
  const changeRole = useChangeMemberRole(workspace.id);
  const [inviting, setInviting] = useState(false);
  const [removing, setRemoving] = useState<Member | null>(null);

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <div className="relative overflow-hidden rounded-2xl border border-border/90 bg-gradient-to-r from-surface via-surface to-surface-subtle/50 p-6 shadow-card-modern">
        <div className="absolute top-0 right-0 h-32 w-64 bg-gradient-to-bl from-blue-500/10 via-emerald-500/5 to-transparent pointer-events-none rounded-tr-2xl" />
        <h1 className="text-2xl sm:text-3xl font-heading font-extrabold tracking-tight text-primary">{t("members.title")}</h1>
        <p className="mt-1 text-sm text-secondary max-w-xl">{t("members.intro")}</p>
      </div>

      {members.isError ? <ErrorMessage error={members.error} /> : null}
      {changeRole.isError ? <ErrorMessage error={changeRole.error} /> : null}
      {members.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}

      {members.data ? (
        <div className="flex flex-col gap-3 rounded-2xl border border-border/80 bg-surface p-5 md:p-6 shadow-card-modern">
          <ul className="flex flex-col divide-y divide-border/60">
            {members.data.map((member) => (
              <li key={member.user_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="font-medium text-primary break-words">
                    {member.display_name}
                    {member.user_id === me.data?.user.id ? (
                      <span className="ml-2 rounded-full bg-surface-subtle px-2 py-0.5 text-xs text-secondary">
                        {t("members.you")}
                      </span>
                    ) : null}
                  </p>
                  <p className="text-xs text-secondary break-all">{member.email}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {owner ? (
                    <select
                      aria-label={t("members.changeRole")}
                      data-testid={`role-select-${member.user_id}`}
                      value={member.role}
                      disabled={changeRole.isPending}
                      onChange={(event) =>
                        changeRole.mutate({
                          userId: member.user_id,
                          role: event.target.value as Role,
                        })
                      }
                      className="min-h-11 rounded-control border border-border bg-surface px-3 py-1.5 text-sm text-primary focus-visible:outline-2 focus-visible:outline-focus"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {t(`workspaces.role.${r}`)}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-sm font-medium text-secondary">
                      {t(`workspaces.role.${member.role}`)}
                    </span>
                  )}
                  {owner ? (
                    <Button variant="secondary" onClick={() => setRemoving(member)}>
                      {t("members.remove")}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {owner ? (
        <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
          <div>
            <Button onClick={() => setInviting(true)}>{t("members.invite")}</Button>
          </div>
          <div className="border-t border-border pt-3">
            <h2 className="text-base font-heading font-semibold text-primary">{t("members.pending")}</h2>
            {invites.isPending ? <p className="mt-2 text-sm text-secondary">{t("common.loading")}</p> : null}
            {invites.data && invites.data.length === 0 ? (
              <p className="mt-2 text-sm text-secondary">{t("members.pendingNone")}</p>
            ) : null}
            {invites.data && invites.data.length > 0 ? (
              <div className="mt-3">
                <PendingInvites invites={invites.data} />
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {inviting ? <InviteSheet onClose={() => setInviting(false)} /> : null}
      {removing ? <RemoveSheet member={removing} onClose={() => setRemoving(null)} /> : null}
    </div>
  );
}

function PendingInvites({ invites }: { invites: { id: string; role: Role; expires_at: string }[] }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const revoke = useRevokeInvite(workspace.id);
  return (
    <ul className="flex flex-col gap-2">
      {invites.map((invite) => (
        <li
          key={invite.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-border bg-surface-subtle p-3"
          data-testid="pending-invite"
        >
          <span className="text-sm font-medium text-primary">
            {t(`workspaces.role.${invite.role}`)}
            {" · "}
            <span className="text-secondary">
              {t("members.expires", { time: new Date(invite.expires_at).toLocaleString() })}
            </span>
          </span>
          <Button
            variant="secondary"
            disabled={revoke.isPending}
            onClick={() => revoke.mutate(invite.id)}
          >
            {t("members.revoke")}
          </Button>
        </li>
      ))}
    </ul>
  );
}

function InviteSheet({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const create = useCreateInvite(workspace.id);
  const [role, setRole] = useState<Role>("manager");
  const [email, setEmail] = useState("");
  const [invite, setInvite] = useState<Invite | null>(null);
  const [copied, setCopied] = useState(false);

  const url = invite ? `${window.location.origin}${invite.invite_path}` : "";

  function copy() {
    if (!url) return;
    try {
      void navigator.clipboard?.writeText(url);
    } catch {
      // Clipboard is unavailable (e.g. an insecure origin); the URL is still shown.
    }
    setCopied(true);
  }

  return (
    <BottomSheet
      title={t("members.inviteTitle")}
      onClose={onClose}
      footer={
        invite ? (
          <div className="flex flex-wrap gap-2">
            <Button block onClick={copy}>
              {copied ? t("members.copied") : t("members.copy")}
            </Button>
            <Button variant="secondary" block onClick={onClose}>
              {t("common.close")}
            </Button>
          </div>
        ) : null
      }
    >
      {invite ? (
        <div className="flex flex-col gap-4">
          <InviteQr value={url} />
          <p data-testid="invite-url" className="text-center text-sm font-mono break-all text-primary bg-surface-subtle p-2 rounded-control border border-border">
            {url}
          </p>
          {invite.email ? (
            <p className="text-center text-xs text-success font-medium">
              {t("members.emailDispatched", { email: invite.email })}
            </p>
          ) : null}
          <p className="text-center text-xs text-secondary leading-relaxed">{t("members.linkHint")}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-primary">{t("members.roleLabel")}</span>
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
              className="min-h-11 rounded-control border border-border bg-surface px-3 py-1.5 text-sm text-primary focus-visible:outline-2 focus-visible:outline-focus"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`workspaces.role.${r}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-primary">{t("members.emailLabel")}</span>
            <input
              type="email"
              placeholder={t("members.emailPlaceholder")}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="min-h-11 rounded-control border border-border bg-surface px-3 py-1.5 text-sm text-primary focus-visible:outline-2 focus-visible:outline-focus"
            />
            <span className="text-xs text-secondary">{t("members.emailHint")}</span>
          </label>
          {create.isError ? <ErrorMessage error={create.error} /> : null}
          <Button
            disabled={create.isPending}
            onClick={() =>
              create.mutate(
                { role, email: email.trim() || undefined },
                { onSuccess: setInvite }
              )
            }
          >
            {t("members.create")}
          </Button>
        </div>
      )}
    </BottomSheet>
  );
}

function RemoveSheet({ member, onClose }: { member: Member; onClose: () => void }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const remove = useRemoveMember(workspace.id);
  return (
    <BottomSheet
      title={t("members.removeTitle")}
      onClose={onClose}
      footer={
        <div className="flex flex-wrap gap-2">
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(member.user_id, { onSettled: onClose })}
          >
            {t("members.removeConfirm")}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm text-primary">{t("members.removeBody")}</p>
        {remove.isError ? <ErrorMessage error={remove.error} /> : null}
      </div>
    </BottomSheet>
  );
}
