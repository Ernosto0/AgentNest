import type { HTMLAttributes } from "react";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`min-w-0 rounded-panel border border-border bg-surface p-5 text-primary ${className}`}
      {...props}
    />
  );
}
