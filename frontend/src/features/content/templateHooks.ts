import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { ContentItem, TemplateBody, TemplateImage } from "@/api/types";
import { contentKey } from "./hooks";

const PREVIEW_DEBOUNCE_MS = 400;

export type PreviewState =
  | { status: "idle"; url: null; error: null }
  | { status: "loading"; url: string | null; error: null }
  | { status: "ready"; url: string; error: null }
  | { status: "error"; url: null; error: AppError };

/**
 * The live preview of a template input. The body is sent after a short pause and only the newest
 * request may show: an older answer that arrives late is dropped. The image is a blob URL, revoked
 * when it is replaced or the sheet closes. Nothing is stored by a preview.
 */
export function useTemplatePreview(ws: string, input: TemplateBody | null): PreviewState {
  const [state, setState] = useState<PreviewState>({ status: "idle", url: null, error: null });
  const urlRef = useRef<string | null>(null);
  const key = input === null ? null : JSON.stringify(input);

  useEffect(() => {
    if (key === null) {
      // The input is incomplete: no request, no stale picture.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState({ status: "idle", url: null, error: null });
      return;
    }
    let current = true;
    const body = JSON.parse(key) as TemplateBody;
    setState((previous) => ({ status: "loading", url: previous.url, error: null }));
    const timer = window.setTimeout(() => {
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/content/template-images/preview", {
          params: { path: { workspace_id: ws } },
          body,
          parseAs: "blob",
        }),
      )
        .then((blob) => {
          if (!current) return;
          const next = URL.createObjectURL(blob as Blob);
          if (urlRef.current) URL.revokeObjectURL(urlRef.current);
          urlRef.current = next;
          setState({ status: "ready", url: next, error: null });
        })
        .catch((error: unknown) => {
          if (!current) return;
          setState({
            status: "error",
            url: null,
            error: error instanceof AppError ? error : new AppError("NETWORK_ERROR", 0),
          });
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [ws, key]);

  useEffect(
    () => () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    },
    [],
  );
  return state;
}

/** Store the rendered card as an ordinary media asset (it is not attached to anything yet). */
export function useCreateTemplateImage(ws: string) {
  return useMutation<TemplateImage, AppError, TemplateBody>({
    mutationFn: (body) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/content/template-images", {
          params: { path: { workspace_id: ws } },
          body,
        }),
      ),
  });
}

/**
 * Draw the image again with the current values. The server makes a new version that is a draft
 * again and needs approval again: nothing is scheduled, approved or published from here.
 */
export function useRerenderTemplateImage(ws: string, id: string) {
  const queryClient = useQueryClient();
  return useMutation<ContentItem, AppError, { expectedVersion: number }>({
    mutationFn: ({ expectedVersion }) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/content-items/{content_id}/template-image/rerender", {
          params: { path: { workspace_id: ws, content_id: id } },
          body: { expected_version: expectedVersion },
        }),
      ),
    onSuccess: (item) => {
      queryClient.setQueryData(contentKey(ws, id), item);
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: ["content-items", ws] }),
        queryClient.invalidateQueries({ queryKey: ["approvals", ws] }),
      ]);
    },
    onError: (error) => {
      if (error.code === "VERSION_CONFLICT" || error.code === "CONFLICT_STATE") {
        return queryClient.invalidateQueries({ queryKey: contentKey(ws, id) });
      }
    },
  });
}
