import type { PrismaClient, Collection } from "../../src/.prisma/client";
import type { CreateCollectionInput, UpdateCollectionInput, ListOptions } from "../types";

const SLUG_REGEX = /^[a-z0-9_-]+$/;

function validateSlug(slug: string): void {
  if (!slug || slug.length > 64) {
    throw new Error("Slug must be 1-64 characters");
  }
  if (!SLUG_REGEX.test(slug)) {
    throw new Error("Slug may only contain lowercase letters, numbers, hyphens, and underscores");
  }
}

export async function createCollection(
  prisma: PrismaClient,
  input: CreateCollectionInput
): Promise<Collection> {
  validateSlug(input.slug);
  if (!input.name?.trim()) {
    throw new Error("Name is required");
  }
  return prisma.collection.create({
    data: {
      name: input.name.trim(),
      slug: input.slug.trim().toLowerCase(),
      description: input.description?.trim() ?? null,
      config: (input.config ?? {}) as unknown as object,
    },
  });
}

export async function getCollections(
  prisma: PrismaClient,
  options: ListOptions
): Promise<{ rows: Collection[]; total: number }> {
  const [total, rows] = await Promise.all([
    prisma.collection.count(),
    prisma.collection.findMany({
      orderBy: { createdAt: "desc" },
      take: options.limit,
      skip: options.offset,
    }),
  ]);

  return { rows, total };
}

function isUuid(value: string): boolean {
  const uuidRegex =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(value);
}

export async function getCollectionByIdOrSlug(
  prisma: PrismaClient,
  idOrSlug: string
): Promise<Collection | null> {
  if (isUuid(idOrSlug)) {
    return prisma.collection.findUnique({ where: { id: idOrSlug } });
  }
  return prisma.collection.findUnique({ where: { slug: idOrSlug } });
}

export async function getCollectionBySlug(
  prisma: PrismaClient,
  slug: string
): Promise<Collection | null> {
  return getCollectionByIdOrSlug(prisma, slug);
}

export async function updateCollection(
  prisma: PrismaClient,
  idOrSlug: string,
  patch: UpdateCollectionInput
): Promise<Collection | null> {
  const existing = await getCollectionByIdOrSlug(prisma, idOrSlug);
  if (!existing) return null;

  if (patch.slug !== undefined) {
    validateSlug(patch.slug);
  }

  const data: Record<string, unknown> = {};

  if (patch.name !== undefined) {
    data.name = patch.name.trim();
  }
  if (patch.slug !== undefined) {
    data.slug = patch.slug.trim().toLowerCase();
  }
  if (patch.description !== undefined) {
    data.description = patch.description?.trim() ?? null;
  }
  if (patch.config !== undefined) {
    data.config = patch.config as unknown as object;
  }

  if (Object.keys(data).length === 0) return existing;

  return prisma.collection.update({
    where: { id: existing.id },
    data,
  });
}

export async function deleteCollection(
  prisma: PrismaClient,
  idOrSlug: string
): Promise<boolean> {
  const existing = await getCollectionByIdOrSlug(prisma, idOrSlug);
  if (!existing) return false;
  await prisma.collection.delete({ where: { id: existing.id } });
  return true;
}
