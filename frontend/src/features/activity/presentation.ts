import type { ComponentType, SVGProps } from "react";
import type { ActivityEntry, ActivityLevel } from "@/api/types";
import {
  BellIcon,
  BookIcon,
  CalendarIcon,
  ChatIcon,
  ImageIcon,
  LinkIcon,
  NoteIcon,
  SendIcon,
  SettingsIcon,
  ShieldCheckIcon,
  SparkIcon,
  UsersIcon,
} from "@/components/icons";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

export const ICONS = {
  alert: BellIcon,
  assistant: SparkIcon,
  calendar: CalendarIcon,
  messages: ChatIcon,
  replies: SendIcon,
  approvals: ShieldCheckIcon,
  content: ImageIcon,
  knowledge: BookIcon,
  commands: NoteIcon,
  accounts: LinkIcon,
  members: UsersIcon,
  system: SettingsIcon,
} satisfies Record<string, Icon>;
export type IconKey = keyof typeof ICONS;

/** The glyph says what kind of thing happened; the tile's colour says how it went. */
export function entryIconKey(entry: Pick<ActivityEntry, "action" | "group">): IconKey {
  if (entry.action.startsWith("security.")) return "alert";
  if (entry.action.startsWith("agent.") || entry.action.startsWith("memory.")) return "assistant";
  if (entry.action.startsWith("calendar.")) return "calendar";
  return entry.group in ICONS ? (entry.group as IconKey) : "system";
}

/** Icon tile tone per level. Info stays quiet so problems stand out. */
export const LEVEL_TILE: Record<ActivityLevel, string> = {
  failure: "bg-danger-subtle text-danger",
  warning: "bg-attention-subtle text-attention",
  success: "bg-success-subtle text-success",
  info: "bg-surface-subtle text-secondary",
};

/** Solid dot for entries listed inside an open group. */
export const LEVEL_DOT: Record<ActivityLevel, string> = {
  failure: "bg-danger",
  warning: "bg-attention",
  success: "bg-success",
  info: "bg-border",
};

/** Inline pill shown only for problems; success and info need no extra word. */
export const LEVEL_PILL: Partial<Record<ActivityLevel, string>> = {
  failure: "bg-danger-subtle text-danger ring-danger/40",
  warning: "bg-attention-subtle text-attention ring-attention/40",
};

/** The workspace-clock time of an entry: "21:18". */
export function timeOf(value: string, language: string, timezone: string): string {
  return new Date(value).toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit", timeZone: timezone });
}

/** The full instant for the details panel, with seconds and the zone name. */
export function fullTimeOf(value: string, language: string, timezone: string): string {
  return new Date(value).toLocaleString(language, {
    dateStyle: "full",
    timeStyle: "medium",
    timeZone: timezone,
  });
}
