interface ReturnLocation { pathname?: string; search?: string; hash?: string }

/** Preserve protected/invite context in router state without an external or login-loop target. */
export function returnDestination(from?: ReturnLocation): string {
  const pathname = from?.pathname;
  if (!pathname || !pathname.startsWith("/") || pathname.startsWith("//") || pathname.includes("\\") || pathname === "/login") return "/";
  return `${pathname}${from.search?.startsWith("?") ? from.search : ""}${from.hash?.startsWith("#") ? from.hash : ""}`;
}
export interface LoginLocationState { from?: ReturnLocation }
