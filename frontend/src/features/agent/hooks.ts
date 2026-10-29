import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { components } from "@/api/schema";
export type Schema<K extends keyof components["schemas"]> = components["schemas"][K];
export const agentKey = (ws: string, account: string) => ["agent", ws, account] as const;
export const ACTIONS = ["dm.send", "comment.reply", "comment.private_reply", "comment.hide", "comment.unhide", "comment.delete", "content.prepare", "content.schedule", "content.publish", "content.cancel"] as const;
export const actionLabelKey = (action: string) => `agent.actions.${action.replaceAll(".", "_")}`;
export function useAgentOverview(ws: string, account: string) {
    return useQuery<Schema<"AgentOverview">, AppError>({ queryKey: [...agentKey(ws, account), "overview"], enabled: !!account, retry: false, refetchInterval: 5000,
        queryFn: () => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent", { params: { path: { workspace_id: ws, account_id: account } } })) });
}
export function useAgentPersonality(ws: string, account: string) {
    return useQuery<Schema<"PersonalityOut">, AppError>({ queryKey: [...agentKey(ws, account), "personality"], enabled: !!account, retry: false,
        queryFn: () => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/personality", { params: { path: { workspace_id: ws, account_id: account } } })) });
}
export function useAgentDelegation(ws: string, account: string) {
    return useQuery<Schema<"DelegationOut"> | null, AppError>({ queryKey: [...agentKey(ws, account), "delegation"], enabled: !!account, retry: false,
        queryFn: () => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/delegation", { params: { path: { workspace_id: ws, account_id: account } } })) });
}
export function useRefreshAgent(ws: string) {
    const client = useQueryClient();
    return () => Promise.all(["agent", "social-accounts", "automation", "conversation", "conversations", "approvals", "approval", "activity", "notifications", "readiness", "content-items"].map(name => client.invalidateQueries({ queryKey: [name, ws] })));
}
export function useSavePersonality(ws: string, account: string) {
    const refresh = useRefreshAgent(ws);
    return useMutation<Schema<"PersonalityOut">, AppError, Schema<"PersonalityChange">>({ mutationFn: body => unwrap(api.PATCH("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/personality", { params: { path: { workspace_id: ws, account_id: account } }, body })), onSuccess: refresh });
}
export function useChangeAgent(ws: string, account: string) {
    const refresh = useRefreshAgent(ws);
    return useMutation<unknown, AppError, {
        command: "activate" | "pause" | "resume";
        version: number;
        requestId: string;
        mode?: "agent" | "legacy";
    }>({ mutationFn: input => {
            const params = { path: { workspace_id: ws, account_id: account } };
            if (input.command === "activate")
                return unwrap(api.POST("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/activate", { params, body: { expected_config_version: input.version, client_request_id: input.requestId, mode: input.mode ?? "agent" } }));
            if (input.command === "pause")
                return unwrap(api.POST("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/pause", { params, body: { expected_config_version: input.version } }));
            return unwrap(api.POST("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/resume", { params, body: { expected_config_version: input.version } }));
        }, onSuccess: refresh });
}
export function usePreviewDelegation(ws: string, account: string) {
    return useMutation<Schema<"DelegationPreview">, AppError, Schema<"DelegationChange">>({ mutationFn: body => unwrap(api.POST("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/delegation/preview", { params: { path: { workspace_id: ws, account_id: account } }, body })) });
}
export function useApplyDelegation(ws: string, account: string) {
    const refresh = useRefreshAgent(ws);
    return useMutation<Schema<"DelegationOut">, AppError, Schema<"DelegationChange">>({ mutationFn: body => unwrap(api.POST("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/delegation/apply", { params: { path: { workspace_id: ws, account_id: account } }, body })), onSuccess: refresh });
}
export function useAgentTasks(ws: string, account: string) {
    return useQuery<Schema<"Page_TaskOut_">, AppError>({ queryKey: [...agentKey(ws, account), "tasks"], enabled: !!account, refetchInterval: 5000, queryFn: () => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/tasks", { params: { path: { workspace_id: ws, account_id: account }, query: { limit: 20 } } })) });
}
export function useSubmitAgentTask(ws: string, account: string) {
    const refresh = useRefreshAgent(ws);
    return useMutation<Schema<"TaskOut">, AppError, Schema<"TaskCreate">>({ mutationFn: body => unwrap(api.POST("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/tasks", { params: { path: { workspace_id: ws, account_id: account } }, body })), onSuccess: refresh });
}
