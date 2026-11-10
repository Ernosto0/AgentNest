import type { ComponentType, SVGProps } from "react";
import type { TFunction } from "i18next";
import {
  AlertIcon,
  CalendarIcon,
  ChatIcon,
  CheckIcon,
  ClockIcon,
  CommentIcon,
  HandIcon,
  HourglassIcon,
  ImageIcon,
  MagnifierIcon,
  PencilIcon,
  ShieldCheckIcon,
  SparkIcon,
  SpinnerIcon,
  XIcon,
} from "@/components/icons";
import { todayIn } from "@/features/reports/dates";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

export type Tone = "success" | "attention" | "danger" | "info" | "neutral";

/**
 * One tone per server state, shared by runs (sessions/tasks), agent actions and linked content.
 * A tone never claims more than the state: only `succeeded`, `completed` and verified `published`
 * read as success; `outcome_unknown` stays informational ("checking"), never green.
 */
const SUCCESS = new Set(["answered", "active", "succeeded", "visible", "completed", "published"]);
const DANGER = new Set(["failed", "blocked"]);
const NEUTRAL = new Set(["expired", "redacted", "deleted", "hidden", "cancelled", "draft"]);
const ATTENTION = new Set(["waiting_owner", "waiting_approval", "needs_human", "waiting_requester", "proposed", "waiting_clarification"]);

export function stateTone(state: string): Tone {
  if (SUCCESS.has(state)) return "success";
  if (DANGER.has(state)) return "danger";
  if (ATTENTION.has(state)) return "attention";
  if (NEUTRAL.has(state)) return "neutral";
  return "info";
}

/** The same label lookup as `WorkState`, so a state reads identically everywhere. */
export function stateLabel(state: string, t: TFunction): string {
  return t(`agentWork.commentState.${state}`, {
    defaultValue: t(`agentWork.state.${state}`, {
      defaultValue: t(`agent.states.${state}`, { defaultValue: t("agentWork.state.unknown") }),
    }),
  });
}

/** Spinning only where the server says work is actually running right now. */
const STATE_ICON: Record<string, { icon: Icon; spins?: boolean }> = {
  running: { icon: SpinnerIcon, spins: true },
  in_progress: { icon: SpinnerIcon, spins: true },
  queued: { icon: ClockIcon },
  authorized: { icon: ShieldCheckIcon },
  sleeping: { icon: HourglassIcon },
  waiting_customer: { icon: ChatIcon },
  waiting_owner: { icon: HandIcon },
  waiting_clarification: { icon: HandIcon },
  waiting_approval: { icon: ShieldCheckIcon },
  waiting_operation: { icon: MagnifierIcon },
  outcome_unknown: { icon: MagnifierIcon },
  proposed: { icon: PencilIcon },
  draft: { icon: PencilIcon },
  scheduled: { icon: CalendarIcon },
  completed: { icon: CheckIcon },
  succeeded: { icon: CheckIcon },
  published: { icon: CheckIcon },
  failed: { icon: AlertIcon },
  cancelled: { icon: XIcon },
};

export function stateIcon(state: string): { icon: Icon; spins?: boolean } {
  return STATE_ICON[state] ?? { icon: SparkIcon };
}

export const TONE_PILL: Record<Tone, string> = {
  success: "bg-success-subtle text-success",
  attention: "bg-attention-subtle text-attention",
  danger: "bg-danger-subtle text-danger",
  info: "bg-info-subtle text-info",
  neutral: "bg-surface-subtle text-secondary",
};

export const TONE_DOT: Record<Tone, string> = {
  success: "bg-success",
  attention: "bg-attention",
  danger: "bg-danger",
  info: "bg-info",
  neutral: "bg-control",
};

/**
 * History filters. Runs and actions use different vocabularies, so each state maps to one
 * plain category; anything unmapped falls into "in progress" rather than looking finished.
 */
export type Category = "needs_you" | "in_progress" | "done" | "failed" | "closed";
export const CATEGORIES: Category[] = ["needs_you", "in_progress", "done", "failed", "closed"];

export function stateCategory(state: string): Category {
  if (["waiting_owner", "waiting_approval", "proposed", "waiting_clarification"].includes(state)) return "needs_you";
  if (["completed", "succeeded"].includes(state)) return "done";
  if (state === "failed") return "failed";
  if (state === "cancelled") return "closed";
  return "in_progress";
}

/** Session states counted as the assistant's open work (owner waits are counted separately). */
export const IN_PROGRESS_RUNS = ["running", "queued", "waiting_operation", "waiting_customer", "sleeping"] as const;

/** Action types by surface; the icon carries the kind of work at a glance. */
export const ACTION_ICON: Record<string, Icon> = {
  dm: ChatIcon,
  comment: CommentIcon,
  content: ImageIcon,
  calendar: CalendarIcon,
};
export const actionSurface = (actionType: string) => actionType.split(".")[0] ?? "";

/** Which of the owner's requests produced each action, from the tasks already loaded. */
export function taskByAction(tasks: { id: string; actions: { action_id: string }[] }[] | undefined): Map<string, string> {
  const map = new Map<string, string>();
  for (const task of tasks ?? []) for (const action of task.actions) map.set(action.action_id, task.id);
  return map;
}

/**
 * Instagram capabilities by what a business owner recognises. Keys come from the provider
 * (`compute_capabilities`, mock capabilities); an unknown key is still listed, under "other".
 */
export const CAPABILITY_GROUPS: { key: "messaging" | "comments" | "publishing"; icon: Icon; capabilities: string[] }[] = [
  { key: "messaging", icon: ChatIcon, capabilities: ["messaging"] },
  { key: "comments", icon: CommentIcon, capabilities: ["comment_read", "comment_reply", "comment_private_reply", "comment_moderate"] },
  { key: "publishing", icon: ImageIcon, capabilities: ["publish_feed_image", "publish_story_image"] },
];
export const KNOWN_CAPABILITIES = new Set(CAPABILITY_GROUPS.flatMap((g) => g.capabilities));

/**
 * The provider capability each delegated action needs. Mirrors `CAPABILITIES` in
 * `backend/app/agent/delegation.py`; it only explains, the server still decides.
 */
export const ACTION_CAPABILITY: Record<string, string | undefined> = {
  "dm.send": "messaging",
  "comment.reply": "comment_reply",
  "comment.private_reply": "comment_private_reply",
  "comment.hide": "comment_moderate",
  "comment.unhide": "comment_moderate",
  "comment.delete": "comment_moderate",
  "content.publish": "publish_feed_image",
};

export function actionsForCapability(capability: string): string[] {
  return Object.entries(ACTION_CAPABILITY)
    .filter(([, needed]) => needed === capability)
    .map(([action]) => action);
}

export type Mode = "automatic" | "ask" | "off";

/** One mode for several actions, or "mixed" when they differ. No policy yet means everything is off. */
export function combinedMode(
  actions: string[],
  policy: { actions: Record<string, { mode: Mode }> } | null | undefined,
): Mode | "mixed" | null {
  if (!actions.length) return null;
  const modes = new Set(actions.map((a) => policy?.actions[a]?.mode ?? "off"));
  return modes.size === 1 ? [...modes][0]! : "mixed";
}

export const MODE_TONE: Record<Mode | "mixed", Tone> = {
  automatic: "success",
  ask: "attention",
  off: "neutral",
  mixed: "info",
};

/** "3 min ago", "yesterday": short, localized, and paired with the absolute time in a tooltip. */
export function relativeTime(iso: string, language: string, now = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const format = new Intl.RelativeTimeFormat(language, { numeric: "auto", style: "short" });
  const abs = Math.abs(seconds);
  if (abs < 60) return format.format(0, "minute");
  if (abs < 3600) return format.format(Math.round(seconds / 60), "minute");
  if (abs < 86_400) return format.format(Math.round(seconds / 3600), "hour");
  return format.format(Math.round(seconds / 86_400), "day");
}

export function absoluteTime(iso: string, language: string, timezone: string): string {
  return new Date(iso).toLocaleString(language, { dateStyle: "medium", timeStyle: "short", timeZone: timezone });
}

export function clockTime(iso: string, language: string, timezone: string): string {
  return new Date(iso).toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit", timeZone: timezone });
}

/** Groups items by their day on the workspace clock, newest day first, keeping input order inside a day. */
export function groupByDay<T>(items: T[], at: (item: T) => string, timezone: string): { day: string; items: T[] }[] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const day = todayIn(timezone, new Date(at(item)));
    groups.set(day, [...(groups.get(day) ?? []), item]);
  }
  return [...groups.entries()].sort(([a], [b]) => (a < b ? 1 : -1)).map(([day, list]) => ({ day, items: list }));
}
