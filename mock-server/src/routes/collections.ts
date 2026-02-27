import { Router, Request, Response, NextFunction } from "express";
import type { Collection } from "../../src/.prisma/client";
import * as collectionsRepo from "../repositories/collections";
import type { AppLocals } from "../types";
import type { CreateCollectionInput, UpdateCollectionInput } from "../types";
import type { HttpError } from "../middleware/errorHandler";

const router = Router();

function getPrisma(req: Request): AppLocals["prisma"] {
  return (req.app.locals as AppLocals).prisma;
}

function mapCollection(row: Collection) {
  return {
    id: row.id,
    name: row.name,
    slug: row.slug,
    description: row.description,
    config: row.config,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

router.post("/", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const body = req.body as CreateCollectionInput;
    const prisma = getPrisma(req);
    const created = await collectionsRepo.createCollection(prisma, body);
    res.status(201).json(mapCollection(created));
  } catch (err) {
    const e = err as Error & { code?: string };
    if (e.code === "23505") {
      const httpErr: HttpError = new Error("A collection with this slug already exists");
      httpErr.statusCode = 409;
      return next(httpErr);
    }
    next(err);
  }
});

router.get("/", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const limit = Math.min(Math.max(parseInt(req.query.limit as string, 10) || 50, 1), 100);
    const offset = Math.max(parseInt(req.query.offset as string, 10) || 0, 0);
    const prisma = getPrisma(req);
    const result = await collectionsRepo.getCollections(prisma, { limit, offset });
    res.json({
      items: result.rows.map(mapCollection),
      total: result.total,
      limit,
      offset,
    });
  } catch (err) {
    next(err);
  }
});

router.get("/:idOrSlug", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const prisma = getPrisma(req);
    const collection = await collectionsRepo.getCollectionByIdOrSlug(
      prisma,
      req.params.idOrSlug
    );
    if (!collection) {
      return res.status(404).json({ error: "Collection not found" });
    }
    res.json(mapCollection(collection));
  } catch (err) {
    next(err);
  }
});

router.put("/:idOrSlug", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const prisma = getPrisma(req);
    const body = req.body as UpdateCollectionInput;
    const updated = await collectionsRepo.updateCollection(prisma, req.params.idOrSlug, body);
    if (!updated) {
      return res.status(404).json({ error: "Collection not found" });
    }
    res.json(mapCollection(updated));
  } catch (err) {
    const e = err as Error & { code?: string };
    if (e.code === "23505") {
      const httpErr: HttpError = new Error("A collection with this slug already exists");
      httpErr.statusCode = 409;
      return next(httpErr);
    }
    next(err);
  }
});

router.delete("/:idOrSlug", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const prisma = getPrisma(req);
    const deleted = await collectionsRepo.deleteCollection(prisma, req.params.idOrSlug);
    if (!deleted) {
      return res.status(404).json({ error: "Collection not found" });
    }
    res.status(204).send();
  } catch (err) {
    next(err);
  }
});

export default router;
