import identity from "./assets/brand/identity.json";
import "./Brand.css";

type BrandProps = {
  variant?: "horizontal" | "wordmark" | "monogram";
  size?: "xs" | "sm" | "md" | "lg";
  tone?: "inherit" | "light" | "dark";
  /** Supply a label for a standalone image; omit inside an already named link. */
  label?: string;
  className?: string;
};

/** Generated from scripts/brand/Brand.tsx. Keep both standalone apps in sync via the generator. */
export function Brand({ variant = "horizontal", size = "md", tone = "inherit", label, className = "" }: BrandProps) {
  return <span
    className={`pivoris-brand pivoris-brand--${size} ${className}`}
    data-tone={tone}
    role={label ? "img" : undefined}
    aria-label={label}
    aria-hidden={label ? undefined : true}
  >
    {variant !== "wordmark" ? <svg className="pivoris-brand__symbol" viewBox="5 -1.5 90 90" width="36" height="36" fill="none" aria-hidden="true" focusable="false">
      <path d={identity.monogram} stroke="currentColor" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
    </svg> : null}
    {variant !== "monogram" ? <svg className="pivoris-brand__wordmark" viewBox={identity.wordmarkViewBox} width={identity.wordmarkWidth} height={identity.wordmarkHeight} fill="currentColor" aria-hidden="true" focusable="false">
      <path d={identity.wordmark} />
    </svg> : null}
  </span>;
}
