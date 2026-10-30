import type { ReactNode } from "react";

/** Centered message for loading and fatal states that happen outside the app shell. */
export function FullScreenStatus({ children }: { children: ReactNode }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="mx-auto flex min-h-dvh max-w-lg flex-col items-center justify-center gap-4 px-4 py-8 text-center text-secondary"
    >
      {children}
    </div>
  );
}
