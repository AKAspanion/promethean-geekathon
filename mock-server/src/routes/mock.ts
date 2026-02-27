import { Router, Request, Response, NextFunction } from "express";
import type { Collection, Record as RecordModel } from "../../src/.prisma/client";
import * as collectionsRepo from "../repositories/collections";
import * as recordsRepo from "../repositories/records";
import type { AppLocals } from "../types";

const router = Router();

function getPrisma(req: Request): AppLocals["prisma"] {
  return (req.app.locals as AppLocals).prisma;
}

declare global {
  namespace Express {
    interface Request {
      collection?: Collection;
    }
  }
}

async function attachCollection(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  const slug = req.params.collectionSlug;
  if (!slug) {
    return next(new Error("collectionSlug is required"));
  }
  const prisma = getPrisma(req);
  const collection = await collectionsRepo.getCollectionBySlug(prisma, slug);
  if (!collection) {
    res.status(404).json({ error: "Collection not found" });
    return;
  }
  req.collection = collection;
  next();
}

function mapRecord(row: RecordModel) {
  return {
    id: row.id,
    data: row.data,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

function getLimitOffset(
  query: Request["query"],
  config: unknown
): { limit: number; offset: number } {
  const configObject =
    config && typeof config === "object"
      ? (config as { defaultLimit?: number | null })
      : {};

  const defaultLimit =
    (typeof configObject.defaultLimit === "number" ? configObject.defaultLimit : null) ?? 50;
  const limit = Math.min(
    Math.max(parseInt(query.limit as string, 10) || defaultLimit, 1),
    100
  );
  const offset = Math.max(parseInt(query.offset as string, 10) || 0, 0);
  return { limit, offset };
}

/**
 * Parse query param q in format "path:value" (object path notation, e.g. name:detroit or name.city:detroit).
 * First colon separates path from value; value may contain colons.
 */
function parseKeyValueQuery(q: unknown): { path: string; value: string } | null {
  if (typeof q !== "string" || !q.trim()) return null;
  const firstColon = q.indexOf(":");
  if (firstColon <= 0) return null;
  const path = q.slice(0, firstColon).trim();
  const value = q.slice(firstColon + 1).trim();
  if (!path) return null;
  return { path, value };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

router.use("/:collectionSlug", attachCollection);

router.get("/:collectionSlug", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const collection = req.collection!;
    const { limit, offset } = getLimitOffset(req.query, collection.config);
    const query = parseKeyValueQuery(req.query.q);
    const prisma = getPrisma(req);
    const result = await recordsRepo.listRecords(prisma, collection.id, {
      limit,
      offset,
      ...(query && { query }),
    });

    const delayConfig =
      collection.config && typeof collection.config === "object"
        ? (collection.config as { responseDelayMs?: number })
        : {};
    const delayMs =
      typeof delayConfig.responseDelayMs === "number" ? delayConfig.responseDelayMs : 0;
    if (delayMs > 0) await delay(delayMs);

    res.json({
      items: result.rows.map(mapRecord),
      total: result.total,
      limit,
      offset,
    });
  } catch (err) {
    next(err);
  }
});

router.post("/:collectionSlug", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const collection = req.collection!;
    const payload = typeof req.body === "object" && req.body !== null ? req.body : {};
    const prisma = getPrisma(req);
    const created = await recordsRepo.createRecord(prisma, collection.id, payload);
    res.status(201).json(mapRecord(created));
  } catch (err) {
    next(err);
  }
});

router.get("/:collectionSlug/:id", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const collection = req.collection!;
    const prisma = getPrisma(req);
    const record = await recordsRepo.getRecordById(prisma, collection.id, req.params.id);
    if (!record) {
      return res.status(404).json({ error: "Record not found" });
    }
    res.json(mapRecord(record));
  } catch (err) {
    next(err);
  }
});

router.put("/:collectionSlug/:id", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const collection = req.collection!;
    const payload = typeof req.body === "object" && req.body !== null ? req.body : {};
    const prisma = getPrisma(req);
    const updated = await recordsRepo.replaceRecord(
      prisma,
      collection.id,
      req.params.id,
      payload
    );
    if (!updated) {
      return res.status(404).json({ error: "Record not found" });
    }
    res.json(mapRecord(updated));
  } catch (err) {
    next(err);
  }
});

router.patch("/:collectionSlug/:id", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const collection = req.collection!;
    const patch = typeof req.body === "object" && req.body !== null ? req.body : {};
    const prisma = getPrisma(req);
    const updated = await recordsRepo.patchRecord(
      prisma,
      collection.id,
      req.params.id,
      patch
    );
    if (!updated) {
      return res.status(404).json({ error: "Record not found" });
    }
    res.json(mapRecord(updated));
  } catch (err) {
    next(err);
  }
});

router.delete("/:collectionSlug/:id", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const collection = req.collection!;
    const prisma = getPrisma(req);
    const deleted = await recordsRepo.deleteRecord(prisma, collection.id, req.params.id);
    if (!deleted) {
      return res.status(404).json({ error: "Record not found" });
    }
    res.status(204).send();
  } catch (err) {
    next(err);
  }
});

export default router;
