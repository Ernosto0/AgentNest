import { Button } from "./Button";

/** Cursor-neutral controls: the feature owns scope, cursor and loading behavior. */
export function Pagination({ label, previousLabel, nextLabel, onPrevious, onNext, pending = false }: { label: string; previousLabel: string; nextLabel: string; onPrevious?: () => void; onNext?: () => void; pending?: boolean }) {
  return <nav aria-label={label} className="flex flex-wrap items-center justify-between gap-3">
    <Button variant="secondary" onClick={onPrevious} disabled={!onPrevious || pending}>{previousLabel}</Button>
    <Button variant="secondary" onClick={onNext} disabled={!onNext || pending}>{nextLabel}</Button>
  </nav>;
}
