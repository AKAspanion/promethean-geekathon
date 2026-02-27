import "dotenv/config";
import express from "express";
import cors from "cors";
import { getPrisma } from "./db/prisma";
import { notFoundHandler, globalErrorHandler } from "./middleware/errorHandler";
import collectionsRouter from "./routes/collections";
import mockRouter from "./routes/mock";
import type { AppLocals } from "./types";

const PORT = parseInt(process.env.PORT ?? "4000", 10);

async function main(): Promise<void> {
  const prisma = getPrisma();
  await prisma.$connect();

  const app = express();
  (app.locals as AppLocals).prisma = prisma;

  app.use(cors());
  app.use(express.json({ limit: "1mb" }));

  app.get("/health", async (_req, res) => {
    try {
      await prisma.$queryRawUnsafe("SELECT 1");
      res.json({ status: "ok", db: "mock_db" });
    } catch {
      res.status(500).json({ status: "error", db: "unreachable" });
    }
  });

  app.use("/collections", collectionsRouter);
  app.use("/mock", mockRouter);

  app.use(notFoundHandler);
  app.use(globalErrorHandler);

  app.listen(PORT, () => {
    console.log(`Mock server running at http://localhost:${PORT} (database: mock_db)`);
  });
}

main().catch((err) => {
  console.error("Failed to start server:", err);
  process.exit(1);
});
