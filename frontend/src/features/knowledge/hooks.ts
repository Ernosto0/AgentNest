import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type {
  Fact,
  FactCandidate,
  FactCreateBody,
  FactPatchBody,
  FactVersion,
  Readiness,
  TemplateItem,
} from "@/api/types";

export const factsKey = (workspaceId: string) => ["facts", workspaceId] as const;
export const templateKey = (workspaceId: string) => ["fact-template", workspaceId] as const;
export const candidatesKey = (workspaceId: string, status: string) =>
  ["fact-candidates", workspaceId, status] as const;
export const readinessKey = (workspaceId: string) => ["readiness", workspaceId] as const;
export const versionsKey = (workspaceId: string, factId: string) =>
  ["fact-versions", workspaceId, factId] as const;

export function useFacts(workspaceId: string) {
  return useQuery<Fact[], AppError>({
    queryKey: factsKey(workspaceId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/facts", {
            params: { path: { workspace_id: workspaceId } },
          }),
        )
      ).items,
  });
}

export function useTemplate(workspaceId: string) {
  return useQuery<TemplateItem[], AppError>({
    queryKey: templateKey(workspaceId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/facts/template", {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
  });
}

export function useReadiness(workspaceId: string) {
  return useQuery<Readiness, AppError>({
    queryKey: readinessKey(workspaceId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/readiness", {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
  });
}

export function useCandidates(workspaceId: string, status: "pending" = "pending") {
  return useQuery<FactCandidate[], AppError>({
    queryKey: candidatesKey(workspaceId, status),
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/fact-candidates", {
            params: { path: { workspace_id: workspaceId }, query: { status } },
          }),
        )
      ).items,
  });
}

export function useFactVersions(workspaceId: string, factId: string | null) {
  return useQuery<FactVersion[], AppError>({
    queryKey: versionsKey(workspaceId, factId ?? "none"),
    enabled: factId !== null,
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/facts/{fact_id}/versions", {
            params: { path: { workspace_id: workspaceId, fact_id: factId ?? "" } },
          }),
        )
      ).items,
  });
}

/** What a save returns: the fact, or (staff) a pending candidate that the owner must decide. */
export type SaveResult = Fact | FactCandidate;

export function isCandidate(result: SaveResult): result is FactCandidate {
  return result.kind === "candidate";
}

/** Everything that depends on facts is refetched after any change. */
function useRefreshKnowledge(workspaceId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: factsKey(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: templateKey(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: ["fact-candidates", workspaceId] }),
      queryClient.invalidateQueries({ queryKey: readinessKey(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: ["fact-versions", workspaceId] }),
    ]);
  };
}

export function useCreateFact(workspaceId: string) {
  const refresh = useRefreshKnowledge(workspaceId);
  return useMutation<SaveResult, AppError, FactCreateBody>({
    mutationFn: (body) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/facts", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export function useUpdateFact(workspaceId: string) {
  const refresh = useRefreshKnowledge(workspaceId);
  return useMutation<SaveResult, AppError, { factId: string; body: FactPatchBody }>({
    mutationFn: ({ factId, body }) =>
      unwrap(
        api.PATCH("/api/v1/workspaces/{workspace_id}/facts/{fact_id}", {
          params: { path: { workspace_id: workspaceId, fact_id: factId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

type Transition = "verify" | "archive" | "restore";

export function useFactTransition(workspaceId: string) {
  const refresh = useRefreshKnowledge(workspaceId);
  return useMutation<Fact, AppError, { factId: string; action: Transition; expectedVersion: number }>({
    mutationFn: ({ factId, action, expectedVersion }) => {
      const path = { workspace_id: workspaceId, fact_id: factId };
      const body = { expected_version: expectedVersion };
      switch (action) {
        case "verify":
          return unwrap(
            api.POST("/api/v1/workspaces/{workspace_id}/facts/{fact_id}/verify", {
              params: { path },
              body,
            }),
          );
        case "archive":
          return unwrap(
            api.POST("/api/v1/workspaces/{workspace_id}/facts/{fact_id}/archive", {
              params: { path },
              body,
            }),
          );
        case "restore":
          return unwrap(
            api.POST("/api/v1/workspaces/{workspace_id}/facts/{fact_id}/restore", {
              params: { path },
              body,
            }),
          );
      }
    },
    onSuccess: refresh,
  });
}

export function useResolveCandidate(workspaceId: string) {
  const refresh = useRefreshKnowledge(workspaceId);
  return useMutation<unknown, AppError, { candidateId: string; action: "accept" | "reject" }>({
    mutationFn: ({ candidateId, action }) => {
      const path = { workspace_id: workspaceId, candidate_id: candidateId };
      return action === "accept"
        ? unwrap(
            api.POST("/api/v1/workspaces/{workspace_id}/fact-candidates/{candidate_id}/accept", {
              params: { path },
            }),
          )
        : unwrap(
            api.POST("/api/v1/workspaces/{workspace_id}/fact-candidates/{candidate_id}/reject", {
              params: { path },
            }),
          );
    },
    onSuccess: refresh,
  });
}
