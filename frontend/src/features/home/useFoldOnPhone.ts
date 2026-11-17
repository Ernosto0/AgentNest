import { useState, useSyncExternalStore } from "react";

const PHONE_QUERY = "(max-width: 767.98px)";

function subscribePhone(onChange: () => void) {
  const query = window.matchMedia?.(PHONE_QUERY);
  query?.addEventListener("change", onChange);
  return () => query?.removeEventListener("change", onChange);
}

/**
 * Secondary Today sections fold away on phones so the first screens hold what needs the owner
 * (waiting items, the assistant box, today's numbers). Wider screens never collapse, and an
 * environment without matchMedia (tests) counts as wide.
 */
export function useFoldOnPhone() {
  const phone = useSyncExternalStore(
    subscribePhone,
    () => window.matchMedia?.(PHONE_QUERY).matches ?? false,
    () => false,
  );
  const [open, setOpen] = useState(false);
  return { folded: phone && !open, foldable: phone, open, toggle: () => setOpen((value) => !value) };
}
