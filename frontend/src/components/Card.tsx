import type { HTMLAttributes } from "react";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`an-card min-w-0 ${className}`}
      {...props}
    />
  );
}
