"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "../api";
import type { CreateCollectionInput } from "../types";

const COLLECTIONS_KEY = ["collections"] as const;

export function useCollectionsList(params?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: [...COLLECTIONS_KEY, "list", params],
    queryFn: () => api.collections.list(params),
  });
}

export function useCollection(idOrSlug: string | null) {
  return useQuery({
    queryKey: [...COLLECTIONS_KEY, idOrSlug],
    queryFn: () => api.collections.get(idOrSlug!),
    enabled: !!idOrSlug,
  });
}

export function useCreateCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateCollectionInput) => api.collections.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  });
}

export function useUpdateCollection(idOrSlug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateCollectionInput) =>
      api.collections.update(idOrSlug, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  });
}

export function useDeleteCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (idOrSlug: string) => api.collections.delete(idOrSlug),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  });
}
