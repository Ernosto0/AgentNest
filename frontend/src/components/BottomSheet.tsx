import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Button } from "./Button";
import { isTopmostModal, registerModal, tabbableElements } from "./modalFocus";

interface BottomSheetProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  description?: string;
  /** Block Escape/backdrop/close during an action whose cancellation is unavailable. */
  dismissible?: boolean;
  initialFocusRef?: RefObject<HTMLElement | null>;
  /** Explicit opener for browsers that do not focus buttons on pointer activation. */
  returnFocusRef?: RefObject<HTMLElement | null>;
}

/**
 * A modal dialog that slides up from the bottom on phones and is centred on desktop.
 * Focus moves into it and returns on close; Escape and the backdrop close it.
 */
export function BottomSheet({ title, onClose, children, footer, description, dismissible = true, initialFocusRef, returnFocusRef }: BottomSheetProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const dismissibleRef = useRef(dismissible);

  // Keep the latest handler without re-running the focus/keyboard effect on every render.
  useEffect(() => {
    onCloseRef.current = onClose;
    dismissibleRef.current = dismissible;
  });

  useEffect(() => {
    const container = panel.current;
    const overlay = root.current;
    if (!container || !overlay) return;
    const unregister = registerModal(overlay, container, initialFocusRef?.current, returnFocusRef?.current);
    const onKey = (event: KeyboardEvent) => {
      if (!isTopmostModal(overlay) || event.defaultPrevented) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (dismissibleRef.current) onCloseRef.current();
      }
      if (event.key === "Tab") {
        const targets = tabbableElements(container);
        const first = targets[0];
        const last = targets.at(-1);
        if (!first) { event.preventDefault(); container.focus(); return; }
        if (event.shiftKey && (document.activeElement === first || !targets.includes(document.activeElement as HTMLElement))) {
          event.preventDefault(); last?.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !targets.includes(document.activeElement as HTMLElement))) {
          event.preventDefault(); first.focus();
        }
      }
    };
    const keepFocusInside = (event: FocusEvent) => {
      if (isTopmostModal(overlay) && !container.contains(event.target as Node)) container.focus();
    };
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("focusin", keepFocusInside);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("focusin", keepFocusInside);
      unregister();
    };
  }, [initialFocusRef, returnFocusRef]);

  return createPortal(
    <div ref={root} className="fixed inset-0 z-40 flex items-end justify-center overscroll-contain md:items-center md:p-6">
      <div className="absolute inset-0 bg-navigation/50" aria-hidden="true" data-sheet-backdrop="" onClick={() => { if (dismissible && isTopmostModal(root.current)) onClose(); }} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? `${titleId}-description` : undefined}
        tabIndex={-1}
        className="relative flex max-h-[calc(100dvh-env(safe-area-inset-top)-1rem)] w-full min-w-0 max-w-lg flex-col rounded-t-dialog bg-surface text-primary shadow-float outline-none md:max-h-[calc(100dvh-3rem)] md:rounded-dialog"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-4 py-3">
          <h2 id={titleId} className="min-w-0 text-lg font-semibold break-words">
            {title}
          </h2>
          <Button
            variant="ghost"
            disabled={!dismissible}
            onClick={onClose}
            className="shrink-0"
          >
            {t("common.close")}
          </Button>
        </div>
        <div className={`min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 ${footer ? "" : "pb-[max(1rem,env(safe-area-inset-bottom))]"}`}>
          {description ? <p id={`${titleId}-description`} className="mb-4 text-body text-secondary">{description}</p> : null}
          {children}
        </div>
        {footer ? (
          <div className="shrink-0 border-t border-border px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
