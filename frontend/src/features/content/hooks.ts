import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type {
  ContentCreateBody,
  ContentItem,
  ContentPatchBody,
  ContentTab,
  ContentType,
  ContentValidation,
  MediaAsset,
} from "@/api/types";
import { newRequestId } from "@/features/commands/hooks";

export const contentListKey = (ws: string, tab: ContentTab) => ["content-items", ws, tab] as const;
export const contentKey = (ws: string, id: string) => ["content-item", ws, id] as const;
export const mediaBlobKey = (ws: string, mediaId: string) => ["media-blob", ws, mediaId] as const;

const LIST_POLL_MS = 4000;
const GENERATION_POLL_MS = 2000;
/** Statuses the server moves on its own: the open item is refreshed while it is in one. */
const MOVING = new Set<ContentItem["status"]>([
  "pending_approval",
  "scheduled",
  "publishing",
  "retry_scheduled",
]);

/** True while the AI draft has not been saved yet (a succeeded run reads `running` until then). */
export function isGenerating(item: Pick<ContentItem, "generation">): boolean {
  const status = item.generation?.status;
  return status === "queued" || status === "running";
}

export function useContentItems(ws: string, tab: ContentTab) {
  return useQuery<ContentItem[], AppError>({
    queryKey: contentListKey(ws, tab),
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/content-items", {
            params: { path: { workspace_id: ws }, query: { tab } },
          }),
        )
      ).items,
    refetchInterval: LIST_POLL_MS,
  });
}

/** One item. Polls while generation has not finished (until `succeeded` or `failed`) or while it moves by itself. */
export function useContentItem(ws: string, id: string, enabled = true) {
  return useQuery<ContentItem, AppError>({
    queryKey: contentKey(ws, id),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/content-items/{content_id}", {
          params: { path: { workspace_id: ws, content_id: id } },
        }),
      ),
    refetchInterval: (query) => {
      const item = query.state.data;
      if (!item) return false;
      if (isGenerating(item)) return GENERATION_POLL_MS;
      return MOVING.has(item.status) ? LIST_POLL_MS : false;
    },
  });
}

function useRefreshContent(ws: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["content-items", ws] });
}

export function useCreateContent(ws: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshContent(ws);
  return useMutation<ContentItem, AppError, ContentCreateBody>({
    mutationFn: (body) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/content-items", {
          params: { path: { workspace_id: ws } },
          body,
        }),
      ),
    onSuccess: (item) => {
      queryClient.setQueryData(contentKey(ws, item.id), item);
      return refresh();
    },
  });
}

export interface GenerateInput {
  content_type: ContentType;
  objective: string;
  notes?: string | null;
}

/**
 * Ask for an AI draft. The `client_request_id` makes a retry return the first draft instead of
 * paying for a second generation, so it stays the same while the inputs do; a changed brief is a
 * different request and gets a new id.
 */
export function useGenerateContent(ws: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshContent(ws);
  const request = useRef<{ key: string; id: string } | null>(null);
  return useMutation<ContentItem, AppError, GenerateInput>({
    mutationFn: (input) => {
      const key = JSON.stringify([input.content_type, input.objective, input.notes ?? null]);
      if (request.current?.key !== key) request.current = { key, id: newRequestId() };
      return unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/content-items/generate", {
          params: { path: { workspace_id: ws } },
          body: { ...input, notes: input.notes ?? null, client_request_id: request.current.id },
        }),
      );
    },
    onSuccess: (item) => {
      queryClient.setQueryData(contentKey(ws, item.id), item);
      return refresh();
    },
  });
}

export type ContentChanges = Omit<ContentPatchBody, "expected_version">;

/**
 * Save changes. `expectedVersion` is the version the user was looking at: a 409
 * `VERSION_CONFLICT` means someone else saved first, so the item is reloaded.
 */
export function usePatchContent(ws: string, id: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshContent(ws);
  return useMutation<ContentItem, AppError, { expectedVersion: number; changes: ContentChanges }>({
    mutationFn: ({ expectedVersion, changes }) =>
      unwrap(
        api.PATCH("/api/v1/workspaces/{workspace_id}/content-items/{content_id}", {
          params: { path: { workspace_id: ws, content_id: id } },
          body: { ...changes, expected_version: expectedVersion },
        }),
      ),
    onSuccess: (item) => {
      queryClient.setQueryData(contentKey(ws, id), item);
      return refresh();
    },
    onError: (error) => {
      if (error.code === "VERSION_CONFLICT" || error.code === "CONFLICT_STATE") {
        return queryClient.invalidateQueries({ queryKey: contentKey(ws, id) });
      }
    },
  });
}

/** The schedule as the API takes it: the owner's wall-clock time (the server converts), or "now". */
export type ScheduleInput = { local_date: string; local_time: string } | "now";

/** Errors after which the item on screen is out of date. */
const STALE_ITEM_CODES = new Set(["VERSION_CONFLICT", "CONFLICT_STATE"]);

function useItemAction<Input>(
  ws: string,
  id: string,
  run: (input: Input) => Promise<ContentItem>,
) {
  const queryClient = useQueryClient();
  const refresh = useRefreshContent(ws);
  return useMutation<ContentItem, AppError, Input>({
    mutationFn: run,
    onSuccess: (item) => {
      queryClient.setQueryData(contentKey(ws, id), item);
      return Promise.all([refresh(), queryClient.invalidateQueries({ queryKey: ["approvals", ws] })]);
    },
    onError: (error) => {
      if (STALE_ITEM_CODES.has(error.code)) {
        return queryClient.invalidateQueries({ queryKey: contentKey(ws, id) });
      }
    },
  });
}

/**
 * Submit a draft. `selfApprove` is true only for someone who may approve (`content.approve`):
 * it schedules the post at once; otherwise the post waits for an approver. `expectedVersion` is
 * the version the owner was looking at.
 */
export function useSubmitContent(ws: string, id: string) {
  return useItemAction<{ schedule: ScheduleInput; selfApprove: boolean; expectedVersion: number }>(
    ws,
    id,
    ({ schedule, selfApprove, expectedVersion }) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/content-items/{content_id}/submit", {
          params: { path: { workspace_id: ws, content_id: id } },
          body: { schedule, self_approve: selfApprove, expected_version: expectedVersion },
        }),
      ),
  );
}

/** Approve a held item again (`on_hold` only). The server binds the approval to version + 1. */
export function useReapproveContent(ws: string, id: string) {
  return useItemAction<{ schedule: ScheduleInput; expectedVersion: number }>(
    ws,
    id,
    ({ schedule, expectedVersion }) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/content-items/{content_id}/reapprove", {
          params: { path: { workspace_id: ws, content_id: id } },
          body: { schedule, expected_version: expectedVersion },
        }),
      ),
  );
}

/** Cancel an item that has not gone out (`content.approve`). */
export function useCancelContent(ws: string, id: string) {
  return useItemAction<void>(ws, id, () =>
    unwrap(
      api.POST("/api/v1/workspaces/{workspace_id}/content-items/{content_id}/cancel", {
        params: { path: { workspace_id: ws, content_id: id } },
      }),
    ),
  );
}

/** A dry run of everything a submit checks (changes nothing). */
export function useValidateContent(ws: string, id: string) {
  return useMutation<ContentValidation, AppError, void>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/content-items/{content_id}/validate", {
          params: { path: { workspace_id: ws, content_id: id } },
          // api-design §2.7 calls the body optional, but the generated type requires `self_approve`
          // (it has a default of false): send it, and no `schedule` (the editor's check skips the schedule rules).
          body: { self_approve: false },
        }),
      ),
  });
}

export function useUploadMedia(ws: string) {
  return useMutation<MediaAsset, AppError, File>({
    mutationFn: (file) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/media", {
          params: { path: { workspace_id: ws } },
          // The generated type describes the multipart field as a string.
          body: { file: file as unknown as string },
          bodySerializer: () => {
            const form = new FormData();
            form.append("file", file);
            return form;
          },
        }),
      ),
  });
}

/**
 * The stored image as a blob URL. The endpoint needs the session, so an <img src> cannot load it
 * directly: it is fetched with the cookie and shown from memory (the URL is revoked on change).
 */
export function useMediaPreview(ws: string, mediaId: string | null) {
  const query = useQuery<Blob, AppError>({
    queryKey: mediaBlobKey(ws, mediaId ?? ""),
    enabled: mediaId !== null,
    staleTime: Infinity,
    queryFn: async () =>
      (await unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/media/{media_id}/content", {
          params: { path: { workspace_id: ws, media_id: mediaId ?? "" } },
          parseAs: "blob",
        }),
      )) as Blob,
  });
  const blob = query.data ?? null;
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (blob === null) return;
    const objectUrl = URL.createObjectURL(blob);
    // An object URL is an external resource: it is created and revoked with the effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUrl(objectUrl);
    return () => {
      URL.revokeObjectURL(objectUrl);
      setUrl(null);
    };
  }, [blob]);
  return { url, isPending: query.isPending && mediaId !== null, error: query.error };
}
