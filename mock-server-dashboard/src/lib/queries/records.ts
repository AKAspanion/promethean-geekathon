"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "../api";

function recordsKey(
  collectionSlug: string,
  params?: { limit?: number; offset?: number; q?: string }
) {
  return ["records", collectionSlug, params] as const;
}

export function useRecordsList(
  collectionSlug: string | null,
  params?: { limit?: number; offset?: number; q?: string }
) {
  return useQuery({
    queryKey: recordsKey(collectionSlug ?? "", params),
    queryFn: () => api.records(collectionSlug!).list(params),
    enabled: !!collectionSlug,
  });
}

export function useRecord(
  collectionSlug: string | null,
  recordId: string | null
) {
  return useQuery({
    queryKey: ["records", collectionSlug, recordId],
    queryFn: () => api.records(collectionSlug!).get(recordId!),
    enabled: !!collectionSlug && !!recordId,
  });
}

export function useCreateRecord(collectionSlug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.records(collectionSlug).create(data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["records", collectionSlug] }),
  });
}

export function useReplaceRecord(collectionSlug: string, recordId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.records(collectionSlug).replace(recordId, data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["records", collectionSlug] }),
  });
}

export function usePatchRecord(collectionSlug: string, recordId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.records(collectionSlug).patch(recordId, data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["records", collectionSlug] }),
  });
}

export function useDeleteRecord(collectionSlug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.records(collectionSlug).delete(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["records", collectionSlug] }),
  });
}
