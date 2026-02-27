const BASE_URL =
  process.env.NEXT_PUBLIC_MOCK_SERVER_URL ?? "http://localhost:4000";

async function fetchApi<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    let message = body;
    try {
      const json = JSON.parse(body) as { error?: string };
      if (json.error) message = json.error;
    } catch {
      // use body as message
    }
    throw new Error(message || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetchApi<{ status: string; db: string }>("/health"),

  collections: {
    list: (params?: { limit?: number; offset?: number }) => {
      const search = new URLSearchParams();
      if (params?.limit != null) search.set("limit", String(params.limit));
      if (params?.offset != null) search.set("offset", String(params.offset));
      const q = search.toString();
      return fetchApi<import("./types").CollectionsListResponse>(
        `/collections${q ? `?${q}` : ""}`
      );
    },
    get: (idOrSlug: string) =>
      fetchApi<import("./types").Collection>(`/collections/${idOrSlug}`),
    create: (body: import("./types").CreateCollectionInput) =>
      fetchApi<import("./types").Collection>("/collections", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    update: (idOrSlug: string, body: import("./types").UpdateCollectionInput) =>
      fetchApi<import("./types").Collection>(`/collections/${idOrSlug}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    delete: (idOrSlug: string) =>
      fetchApi<void>(`/collections/${idOrSlug}`, { method: "DELETE" }),
  },

  records: (collectionSlug: string) => ({
    list: (params?: { limit?: number; offset?: number; q?: string }) => {
      const search = new URLSearchParams();
      if (params?.limit != null) search.set("limit", String(params.limit));
      if (params?.offset != null) search.set("offset", String(params.offset));
      if (params?.q != null && params.q.trim() !== "") search.set("q", params.q.trim());
      const q = search.toString();
      return fetchApi<import("./types").RecordsListResponse>(
        `/mock/${collectionSlug}${q ? `?${q}` : ""}`
      );
    },
    get: (id: string) =>
      fetchApi<import("./types").RecordItem>(
        `/mock/${collectionSlug}/${id}`
      ),
    create: (data: Record<string, unknown>) =>
      fetchApi<import("./types").RecordItem>(`/mock/${collectionSlug}`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    replace: (id: string, data: Record<string, unknown>) =>
      fetchApi<import("./types").RecordItem>(
        `/mock/${collectionSlug}/${id}`,
        {
          method: "PUT",
          body: JSON.stringify(data),
        }
      ),
    patch: (id: string, data: Record<string, unknown>) =>
      fetchApi<import("./types").RecordItem>(
        `/mock/${collectionSlug}/${id}`,
        {
          method: "PATCH",
          body: JSON.stringify(data),
        }
      ),
    delete: (id: string) =>
      fetchApi<void>(`/mock/${collectionSlug}/${id}`, {
        method: "DELETE",
      }),
    bulkCreate: (data: Record<string, unknown>[]) =>
      fetchApi<import("./types").BulkCreateResponse>(
        `/mock/${collectionSlug}/bulk`,
        {
          method: "POST",
          body: JSON.stringify(data),
        }
      ),
  }),
};
