import { getPool } from "./pool";

const INIT_SQL = `
-- Enable UUID extension (Postgres 13+ has gen_random_uuid() built-in; older versions may need uuid-ossp)
CREATE TABLE IF NOT EXISTS collections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  description TEXT,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_collections_slug ON collections(slug);

CREATE TABLE IF NOT EXISTS records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_records_collection_id ON records(collection_id);
`;

export async function initDb(): Promise<void> {
  const pool = getPool();
  await pool.query(INIT_SQL);
  console.log("Database tables initialized (mock_db).");
}

async function main(): Promise<void> {
  try {
    await initDb();
    process.exit(0);
  } catch (err) {
    console.error("Init failed:", err);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
