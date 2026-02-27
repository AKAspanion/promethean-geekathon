import { Request, Response, NextFunction } from "express";

export interface HttpError extends Error {
  statusCode?: number;
}

export function notFoundHandler(_req: Request, res: Response): void {
  res.status(404).json({ error: "Not found" });
}

export function globalErrorHandler(
  err: HttpError,
  _req: Request,
  res: Response,
  _next: NextFunction
): void {
  const status = err.statusCode ?? 500;
  const message = err.message ?? "Internal server error";
  if (status >= 500) {
    console.error("Server error:", err);
  }
  res.status(status).json({ error: message });
}
