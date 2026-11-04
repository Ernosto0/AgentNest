import type { HTMLAttributes } from "react";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`min-w-0 rounded-2xl border border-border/80 bg-surface p-5 text-primary shadow-card-modern transition-all duration-200 ${className}`}
      {...props}
    />
  );
}
