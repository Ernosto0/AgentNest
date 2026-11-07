import { createContext, useContext, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";
import { useTranslation } from "react-i18next";

const DirtyContext = createContext<((id: string, dirty: boolean) => void) | null>(null);

/** Register text only for this mounted workspace. Never store customer text in browser storage. */
export function DirtyForms({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [forms, setForms] = useState<Set<string>>(new Set());
  const register = useMemo(() => (id: string, dirty: boolean) => setForms(current => {
    if (current.has(id) === dirty) return current;
    const next = new Set(current);
    if (dirty) next.add(id); else next.delete(id);
    return next;
  }), []);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => forms.size > 0 &&
    (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search));
  useEffect(() => {
    if (blocker.state === "blocked") {
      if (window.confirm(t("core.discardChanges"))) blocker.proceed(); else blocker.reset();
    }
  }, [blocker, t]);
  useBeforeUnload(event => { if (forms.size) { event.preventDefault(); event.returnValue = ""; } });
  return <DirtyContext.Provider value={register}>{children}</DirtyContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useDirtyForm(dirty: boolean) {
  const register = useContext(DirtyContext);
  const id = useId();
  useEffect(() => { register?.(id, dirty); return () => register?.(id, false); }, [register, id, dirty]);
}
