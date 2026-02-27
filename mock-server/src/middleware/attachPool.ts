// No-op middleware kept for backwards compatibility.
// Prisma client is attached in server bootstrap via app.locals.

import { Request, Response, NextFunction } from "express";

export function attachPool(_req: Request, _res: Response, next: NextFunction): void {
  next();
}
