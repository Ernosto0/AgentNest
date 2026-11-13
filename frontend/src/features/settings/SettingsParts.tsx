import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRightIcon } from "@/components/icons";
import { FOCUS } from "@/features/home/DashboardPanel";

export { FOCUS };

/** A plain link styled as a quiet secondary button (navigation stays a link, never a button). */
export const LINK_BUTTON = `inline-flex min-h-11 shrink-0 items-center justify-center gap-1.5 rounded-control border border-border bg-surface px-3.5 text-body font-semibold text-primary transition-colors duration-150 hover:bg-surface-subtle sm:min-h-10 ${FOCUS}`;

/** Inline text action inside a row ("Edit", "Show more"). Keeps a 44 px hit area on touch. */
export const TEXT_ACTION = `inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-control px-2.5 text-body font-semibold text-action transition-colors duration-150 hover:bg-surface-subtle pointer-coarse:min-h-11 ${FOCUS}`;

/**
 * A top-level settings group: an anchor target with its own heading and one line of context.
 * The heading is focusable so the section navigation can move keyboard focus with the scroll.
 */
export function SettingsSection({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} data-settings-section className="flex min-w-0 scroll-mt-6 flex-col gap-4 md:scroll-mt-24">
      <div className="min-w-0">
        <h2 id={`${id}-title`} tabIndex={-1} className="font-heading text-lg leading-snug font-semibold tracking-tight text-primary outline-none">
          {title}
        </h2>
        {description ? <p className="mt-1 max-w-prose text-body text-secondary">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

/** A white working surface. Rows inside are separated by hairlines rather than nested cards. */
export function SettingsPanel({
  as: Tag = "div",
  tone = "surface",
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLElement> & { as?: "div" | "section"; tone?: "surface" | "danger" | "attention" }) {
  const toneClass =
    tone === "danger" ? "border-danger/35 bg-surface" : tone === "attention" ? "border-attention/40 bg-attention-subtle/40" : "border-border bg-surface";
  return (
    <Tag {...props} className={`flex min-w-0 flex-col rounded-2xl border ${toneClass} ${className}`}>
      {children}
    </Tag>
  );
}

/** Panel title row: icon tile, heading, optional description and one trailing action. */
export function PanelTitle({
  id,
  icon,
  title,
  description,
  action,
  iconTone = "neutral",
}: {
  id?: string;
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  iconTone?: "neutral" | "danger";
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-4 gap-y-3 px-4 pt-4 pb-3 sm:px-5 sm:pt-5">
      <div className="flex min-w-0 flex-1 basis-56 items-start gap-3">
        {icon ? (
          <span
            aria-hidden="true"
            className={`flex size-8 shrink-0 items-center justify-center rounded-lg text-base ${
              iconTone === "danger" ? "bg-danger-subtle text-danger" : "bg-surface-subtle text-action"
            }`}
          >
            {icon}
          </span>
        ) : null}
        <div className="min-w-0 pt-1">
          <h3 id={id} className="font-heading text-base leading-snug font-semibold tracking-tight text-primary">
            {title}
          </h3>
          {description ? <div className="mt-0.5 text-metadata text-secondary">{description}</div> : null}
        </div>
      </div>
      {action ? <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div> : null}
    </div>
  );
}

/**
 * One setting: label and explanation on the left, its value or control on the right
 * (stacked on phones). Rows sit inside a panel and are divided by hairlines.
 */
export function SettingRow({
  label,
  labelId,
  description,
  children,
  align = "center",
  className = "",
}: {
  label: ReactNode;
  labelId?: string;
  description?: ReactNode;
  children?: ReactNode;
  align?: "center" | "start";
  className?: string;
}) {
  return (
    <div
      className={`flex min-w-0 flex-col gap-3 border-t border-border/70 px-4 py-4 sm:flex-row sm:justify-between sm:gap-6 sm:px-5 ${
        align === "center" ? "sm:items-center" : "sm:items-start"
      } ${className}`}
    >
      <div className="min-w-0 flex-1">
        <p id={labelId} className="text-body font-semibold text-primary">
          {label}
        </p>
        {description ? <div className="mt-0.5 max-w-prose text-metadata text-secondary">{description}</div> : null}
      </div>
      {children !== undefined ? <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">{children}</div> : null}
    </div>
  );
}

/** A read-only fact as a description-list row: term on the left, value on the right. */
export function DetailRow({ term, children, hint }: { term: string; children: ReactNode; hint?: string }) {
  return (
    <div className="grid min-w-0 gap-1 border-t border-border/70 px-4 py-3.5 sm:grid-cols-[minmax(9rem,14rem)_minmax(0,1fr)] sm:gap-6 sm:px-5">
      <dt className="text-metadata font-medium text-secondary sm:pt-px">{term}</dt>
      <dd className="min-w-0 text-body font-medium text-primary [overflow-wrap:anywhere]">
        {children}
        {hint ? <p className="mt-0.5 text-metadata font-normal text-secondary">{hint}</p> : null}
      </dd>
    </div>
  );
}

/** A navigation row to another settings page: icon, label, context and a chevron. */
export function LinkRow({
  to,
  icon,
  label,
  description,
  meta,
}: {
  to: string;
  icon: ReactNode;
  label: string;
  description?: string;
  meta?: ReactNode;
}) {
  return (
    <Link
      to={to}
      className={`group flex min-h-14 min-w-0 items-center gap-3 border-t border-border/70 px-4 py-3.5 transition-colors duration-150 first:border-t-0 hover:bg-surface-subtle/60 sm:px-5 ${FOCUS} focus-visible:-outline-offset-2`}
    >
      <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-subtle text-base text-action">
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-body font-semibold text-primary">{label}</span>
        {description ? <span className="block text-metadata text-secondary">{description}</span> : null}
      </span>
      {meta ? <span className="hidden shrink-0 text-metadata text-secondary sm:inline">{meta}</span> : null}
      <ChevronRightIcon aria-hidden="true" className="shrink-0 text-lg text-secondary transition-transform duration-150 group-hover:translate-x-0.5 motion-reduce:transition-none" />
    </Link>
  );
}

export interface SectionLink {
  id: string;
  label: string;
}

/**
 * In-page section navigation: a sticky list beside the content from 1024 px, a scrolling strip
 * above it on smaller screens. The highlighted entry follows the scroll position.
 */
export function SectionNav({ sections }: { sections: SectionLink[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [active, setActive] = useState(() => {
    const fromHash = window.location.hash.slice(1);
    return sections.find((section) => section.id === fromHash)?.id ?? sections[0]?.id ?? "";
  });
  // While a click (or a deep link) is scrolling to a section, that section stays highlighted; the
  // scroll position would otherwise pass through the sections in between and flip the highlight.
  const lock = useRef<{ settle: number | null } | null>(null);

  useEffect(() => {
    // The current section is the last one whose top has passed the reading line below the
    // sticky top area; at the very bottom of the page, the final section short enough to never
    // reach that line would otherwise never be highlighted.
    const READING_LINE = 140;
    const measure = () => {
      let current = sections[0]?.id ?? "";
      for (const section of sections) {
        const element = document.getElementById(section.id);
        if (element && element.getBoundingClientRect().top <= READING_LINE) current = section.id;
      }
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      if (atBottom && window.scrollY > 0) current = sections[sections.length - 1]?.id ?? current;
      setActive(current);
    };

    let frame = 0;
    const onScroll = () => {
      if (lock.current) {
        // Keep the clicked section until the scroll comes to rest; the next scroll measures again.
        if (lock.current.settle !== null) window.clearTimeout(lock.current.settle);
        lock.current.settle = window.setTimeout(() => {
          lock.current = null;
        }, 150);
        return;
      }
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        measure();
      });
    };
    // A deep link (#security) is scrolled to by the page itself; hold its highlight until it lands.
    if (sections.some((section) => section.id === window.location.hash.slice(1))) {
      lock.current = { settle: window.setTimeout(() => (lock.current = null), 400) };
    } else {
      measure();
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
      if (lock.current?.settle != null) window.clearTimeout(lock.current.settle);
      lock.current = null;
    };
  }, [sections]);

  const go = (id: string) => {
    const target = document.getElementById(id);
    if (!target) return;
    setActive(id);
    if (lock.current?.settle != null) window.clearTimeout(lock.current.settle);
    lock.current = { settle: window.setTimeout(() => (lock.current = null), 400) };
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "start" });
    document.getElementById(`${id}-title`)?.focus({ preventScroll: true });
    // Keep the section in the address bar so it can be shared or reloaded; same route, no reset.
    void navigate({ hash: id }, { replace: true, preventScrollReset: true });
  };

  return (
    <nav aria-label={t("settings.nav.label")} className="min-w-0 lg:sticky lg:top-24 lg:self-start">
      <ul className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] lg:mx-0 lg:flex-col lg:gap-0.5 lg:overflow-visible lg:px-0 lg:pb-0">
        {sections.map((section) => {
          const current = section.id === active;
          return (
            <li key={section.id} className="shrink-0">
              <a
                href={`#${section.id}`}
                aria-current={current ? "location" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  go(section.id);
                }}
                className={`flex min-h-10 items-center rounded-full border px-3.5 text-body font-medium whitespace-nowrap transition-colors duration-150 pointer-coarse:min-h-11 lg:rounded-lg lg:border-transparent lg:px-3 ${FOCUS} ${
                  current
                    ? "border-action/30 bg-assistant text-primary lg:bg-assistant lg:font-semibold"
                    : "border-border bg-surface text-secondary hover:bg-surface-subtle hover:text-primary lg:bg-transparent"
                }`}
              >
                {section.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
