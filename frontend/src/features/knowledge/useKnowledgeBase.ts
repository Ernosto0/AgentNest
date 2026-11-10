import { useCandidates, useFacts, useReadiness, useTemplate } from "./hooks";
import { neededIdentifiers, summarizeCategories } from "./model";

export const knowledgeBase = (workspaceId: string) => `/w/${workspaceId}/more/knowledge`;

/** Everything the knowledge screens read, fetched once and shared through the query cache. */
export function useKnowledgeBase(workspaceId: string) {
  const template = useTemplate(workspaceId);
  const facts = useFacts(workspaceId);
  const candidates = useCandidates(workspaceId);
  const readiness = useReadiness(workspaceId);
  const loaded = template.data && facts.data ? { template: template.data, facts: facts.data } : null;
  return {
    template,
    facts,
    candidates,
    readiness,
    loaded,
    needed: neededIdentifiers(readiness.data),
    summaries: loaded ? summarizeCategories(loaded.template, loaded.facts, readiness.data) : null,
    error: template.error ?? facts.error,
  };
}
