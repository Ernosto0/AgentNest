import { createContext, useContext } from "react";
import type { Role, Workspace } from "@/api/types";

export interface CurrentWorkspace {
  workspace: Workspace;
  role: Role;
}

export const CurrentWorkspaceContext = createContext<CurrentWorkspace | null>(null);

export function useCurrentWorkspace(): CurrentWorkspace {
  const value = useContext(CurrentWorkspaceContext);
  if (value === null) throw new Error("useCurrentWorkspace must be used inside a workspace route");
  return value;
}
