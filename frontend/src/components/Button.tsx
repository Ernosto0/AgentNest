import { useId, type ButtonHTMLAttributes, type Ref } from "react";
import { SpinnerIcon } from "./icons";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-action text-on-action enabled:hover:bg-action-hover",
  secondary: "border border-control bg-surface text-primary enabled:hover:bg-surface-subtle",
  ghost: "bg-transparent text-primary enabled:hover:bg-surface-subtle",
  danger: "bg-danger text-on-action enabled:hover:bg-danger-hover",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  block?: boolean;
  /** The label remains visible; callers may supply a localized pending label as children. */
  pending?: boolean;
  /** Visible explanation, also associated with a disabled or pending control. */
  disabledReason?: string;
  ref?: Ref<HTMLButtonElement>;
}

/** Touch target of at least 44 px (ADR-020). Defaults to type="button" so it never submits by accident. */
export function Button({
  variant = "primary",
  block = false,
  type = "button",
  className = "",
  pending = false,
  disabled = false,
  disabledReason,
  children,
  "aria-describedby": describedBy,
  ...props
}: ButtonProps) {
  const reasonId = useId();
  const control = (
    <button
      {...props}
      type={type}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      aria-describedby={[describedBy, disabledReason ? reasonId : undefined].filter(Boolean).join(" ") || undefined}
      className={[
        "inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-control px-4 py-2 text-form font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        "disabled:cursor-not-allowed disabled:opacity-60",
        block ? "w-full" : "",
        VARIANTS[variant],
        className,
      ].join(" ")}
    >
      {pending ? <SpinnerIcon className="shrink-0 motion-safe:animate-spin" /> : null}
      {children}
    </button>
  );
  return <>{control}{disabledReason ? <span id={reasonId} className="block text-metadata text-secondary">{disabledReason}</span> : null}</>;
}
