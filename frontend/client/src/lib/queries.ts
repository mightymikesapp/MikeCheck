import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mikeCheckApi } from './api';

// Query Keys
export const QUERY_KEYS = {
  citation: (citation: string) => ['citation', citation],
  search: (query: string) => ['search', query],
  research: (citations: string[]) => ['research', citations],
};

// Hooks
export function useAnalyzeCitation(citation: string | null) {
  return useQuery({
    queryKey: QUERY_KEYS.citation(citation || ''),
    queryFn: () => mikeCheckApi.analyzeCitation(citation!),
    enabled: !!citation,
    staleTime: 1000 * 60 * 60, // 1 hour
  });
}

export function useSearchSimilar(query: string) {
  return useQuery({
    queryKey: QUERY_KEYS.search(query),
    queryFn: () => mikeCheckApi.searchSimilar(query),
    enabled: !!query && query.length > 3,
  });
}

export function useResearchMutation() {
  return useMutation({
    mutationFn: (params: { citations: string[], keyQuestions?: string[] }) => 
      mikeCheckApi.runResearch(params.citations, params.keyQuestions),
  });
}

export function useUploadDocumentMutation() {
  return useMutation({
    mutationFn: (file: File) => mikeCheckApi.uploadDocument(file),
  });
}
