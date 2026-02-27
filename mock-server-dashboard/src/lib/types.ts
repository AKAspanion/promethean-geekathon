export interface Collection {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  config: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface CreateCollectionInput {
  name: string;
  slug: string;
  description?: string;
  config?: Record<string, unknown>;
}

export interface UpdateCollectionInput {
  name?: string;
  slug?: string;
  description?: string;
  config?: Record<string, unknown>;
}

export interface CollectionsListResponse {
  items: Collection[];
  total: number;
  limit: number;
  offset: number;
}

export interface RecordItem {
  id: string;
  data: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface RecordsListResponse {
  items: RecordItem[];
  total: number;
  limit: number;
  offset: number;
}
