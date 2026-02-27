import type { PrismaClient, Record as RecordModel } from "../../src/.prisma/client";
import type { ListOptions } from "../types";

const PATH_SEGMENT_REGEX = /^[a-zA-Z0-9_]+$/;

/** Path with ".*" at the end means "array contains value" (e.g. cities.*:detroit). */
const ARRAY_CONTAINS_SUFFIX = ".*";

/** Segment used to indicate \"any element of array\" (e.g. weather.[].result.main). */
const ARRAY_ANY_SEGMENT = "[]";

interface PathCondition {
  /** Either a JSON path expression (to be wrapped) or a full boolean SQL condition. */
  sql: string;
  /** When true, sql is a complete condition that already compares against $2. */
  isFullCondition: boolean;
  /** When true (and not full), use @> to_jsonb($2::text) instead of = $2. */
  useContainsOperator: boolean;
}

/**
 * Builds a safe SQL expression / condition for JSON path comparison.
 *
 * Supports:
 * - Object path: name, name.city → data->>'name', data->'name'->>'city'
 * - Array index: cities.0 → data->'cities'->>'0' (first element)
 * - Array contains (primitive): cities.* → data->'cities' @> to_jsonb($2::text)
 * - Any element in array has nested key equal to value:
 *   weather.[].result.main → EXISTS (SELECT 1 FROM jsonb_array_elements(data->'weather') elem WHERE elem->'result'->>'main' = $2)
 */
function buildDataPathCondition(path: string): PathCondition {
  const arrayContains = path.endsWith(ARRAY_CONTAINS_SUFFIX);
  const pathToUse = arrayContains ? path.slice(0, -ARRAY_CONTAINS_SUFFIX.length) : path;
  const segments = pathToUse.split(".").filter(Boolean);
  if (segments.length === 0) throw new Error("Query path cannot be empty");

  const anyIndex = segments.indexOf(ARRAY_ANY_SEGMENT);
  if (anyIndex !== -1) {
    if (arrayContains) {
      throw new Error("Path cannot use both [] and .* in the same query");
    }
    // Only support a single [] for now.
    if (segments.indexOf(ARRAY_ANY_SEGMENT, anyIndex + 1) !== -1) {
      throw new Error("Path can contain at most one [] segment");
    }
  }

  for (const seg of segments) {
    if (seg === ARRAY_ANY_SEGMENT) continue;
    if (!PATH_SEGMENT_REGEX.test(seg)) {
      throw new Error(`Invalid query path segment: ${seg}`);
    }
  }

  // Any-element-of-array semantics via [].
  if (anyIndex !== -1) {
    const before = segments.slice(0, anyIndex);
    const after = segments.slice(anyIndex + 1);
    if (after.length === 0) {
      throw new Error("Path with [] must have a nested key after []");
    }

    const escape = (s: string) => `'${s.replace(/'/g, "''")}'`;

    // data->'weather' or just data if path starts with [].
    const beforeEscaped = before.map(escape);
    const arrayExpr =
      beforeEscaped.length === 0
        ? "data"
        : `data->${beforeEscaped.join("->")}`;

    const afterEscaped = after.map(escape);
    const valueExpr =
      afterEscaped.length === 1
        ? `elem->>${afterEscaped[0]}`
        : `elem->${afterEscaped.slice(0, -1).join("->")}->>${
            afterEscaped[afterEscaped.length - 1]
          }`;

    const sql = `EXISTS (SELECT 1 FROM jsonb_array_elements(${arrayExpr}) AS elem WHERE ${valueExpr} = $2)`;
    return { sql, isFullCondition: true, useContainsOperator: false };
  }

  // Primitive array contains via .* suffix.
  if (arrayContains) {
    const escaped = segments.map((s) => `'${s.replace(/'/g, "''")}'`);
    const pathSql = `data->${escaped.join("->")}`;
    return { sql: pathSql, isFullCondition: false, useContainsOperator: true };
  }

  // Simple equality on scalar value.
  const escaped = segments.map((s) => `'${s.replace(/'/g, "''")}'`);
  const pathSql =
    escaped.length === 1
      ? `data->>${escaped[0]}`
      : `data->${escaped.slice(0, -1).join("->")}->>${
          escaped[escaped.length - 1]
        }`;
  return { sql: pathSql, isFullCondition: false, useContainsOperator: false };
}

export async function listRecords(
  prisma: PrismaClient,
  collectionId: string,
  options: ListOptions
): Promise<{ rows: RecordModel[]; total: number }> {
  const query = options.query;
  if (!query?.path || query.value === undefined) {
    const [total, rows] = await Promise.all([
      prisma.record.count({ where: { collectionId } }),
      prisma.record.findMany({
        where: { collectionId },
        orderBy: { createdAt: "desc" },
        take: options.limit,
        skip: options.offset,
      }),
    ]);
    return { rows, total };
  }

  const { sql, isFullCondition, useContainsOperator } = buildDataPathCondition(
    query.path
  );
  const condition = isFullCondition
    ? sql
    : useContainsOperator
      ? `${sql} @> to_jsonb($2::text)`
      : `${sql} = $2`;
  const countResult = await prisma.$queryRawUnsafe<[{ count: bigint }]>(
    `SELECT COUNT(*)::bigint as count FROM "Record" WHERE "collectionId" = $1 AND ${condition}`,
    collectionId,
    query.value
  );
  const total = Number(countResult[0]?.count ?? 0);
  const rows = await prisma.$queryRawUnsafe<
    Array<{
      id: string;
      collectionId: string;
      data: unknown;
      createdAt: Date;
      updatedAt: Date;
    }>
  >(
    `SELECT * FROM "Record" WHERE "collectionId" = $1 AND ${condition} ORDER BY "createdAt" DESC LIMIT $3 OFFSET $4`,
    collectionId,
    query.value,
    options.limit,
    options.offset
  );
  return {
    rows: rows as RecordModel[],
    total,
  };
}

export async function createRecord(
  prisma: PrismaClient,
  collectionId: string,
  data: Record<string, unknown>
): Promise<RecordModel> {
  return prisma.record.create({
    data: {
      collectionId,
      data: (data ?? {}) as unknown as object,
    },
  });
}

export async function getRecordById(
  prisma: PrismaClient,
  collectionId: string,
  recordId: string
): Promise<RecordModel | null> {
  return prisma.record.findFirst({
    where: { id: recordId, collectionId },
  });
}

export async function replaceRecord(
  prisma: PrismaClient,
  collectionId: string,
  recordId: string,
  data: Record<string, unknown>
): Promise<RecordModel | null> {
  const existing = await getRecordById(prisma, collectionId, recordId);
  if (!existing) return null;

  return prisma.record.update({
    where: { id: existing.id },
    data: {
      data: (data ?? {}) as unknown as object,
    },
  });
}

export async function patchRecord(
  prisma: PrismaClient,
  collectionId: string,
  recordId: string,
  patch: Record<string, unknown>
): Promise<RecordModel | null> {
  const existing = await getRecordById(prisma, collectionId, recordId);
  if (!existing) return null;
  const merged = { ...(existing.data as Record<string, unknown>), ...patch };
  return replaceRecord(prisma, collectionId, recordId, merged);
}

export async function deleteRecord(
  prisma: PrismaClient,
  collectionId: string,
  recordId: string
): Promise<boolean> {
  const existing = await getRecordById(prisma, collectionId, recordId);
  if (!existing) return false;
  await prisma.record.delete({ where: { id: existing.id } });
  return true;
}
