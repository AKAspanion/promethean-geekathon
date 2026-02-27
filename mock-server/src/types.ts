import type { PrismaClient } from "../src/.prisma/client";

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

/** Query by key path and value, e.g. { path: "name", value: "detroit" } or { path: "name.city", value: "detroit" } */
export interface KeyValueQuery {
  path: string;
  value: string;
}

export interface ListOptions {
  limit: number;
  offset: number;
  query?: KeyValueQuery;
}

export interface AppLocals {
  prisma: PrismaClient;
}
