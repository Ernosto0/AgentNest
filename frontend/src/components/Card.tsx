import type { HTMLAttributes } from "react";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`min-w-0 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200 ${className}`}
      {...props}
    />
  );
}
