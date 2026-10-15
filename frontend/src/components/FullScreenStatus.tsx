import type { ReactNode } from "react";

/** Centered message for loading and fatal states that happen outside the app shell. */
export function FullScreenStatus({ children }: { children: ReactNode }) {
  return (
    <div
      role="status"
      className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center gap-4 px-4 text-center text-slate-700"
    >
      {children}
    </div>
  );
}
