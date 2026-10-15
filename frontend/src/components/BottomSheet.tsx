import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

interface BottomSheetProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * A modal dialog that slides up from the bottom on phones and is centred on desktop.
 * Focus moves into it and returns on close; Escape and the backdrop close it.
 */
export function BottomSheet({ title, onClose, children, footer }: BottomSheetProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  // Keep the latest handler without re-running the focus/keyboard effect on every render.
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus();
    const scrollBefore = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = scrollBefore;
      previous?.focus();
    };
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-40 flex items-end justify-center md:items-center">
      <div className="absolute inset-0 bg-slate-900/50" aria-hidden="true" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-lg flex-col rounded-t-2xl bg-white shadow-xl outline-none md:rounded-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 id={titleId} className="min-w-0 text-lg font-semibold break-words">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 shrink-0 rounded-lg px-3 text-base font-medium text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            {t("common.close")}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
        {footer ? (
          <div className="border-t border-slate-200 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
