# Mock Server

Extensible mock API server with dynamic endpoints and PostgreSQL storage. Data is stored in the **mock_db** database. You define custom “collections” (endpoints) via the API; each collection supports full CRUD on JSON records.

## Requirements

- Node.js 18+
- PostgreSQL with a database named **mock_db**

Create the database if needed:

```bash
createdb mock_db
```

## Setup

```bash
cd mock-server
cp .env.example .env
# Edit .env and set DATABASE_URL (default: postgres://localhost:5432/mock_db)
npm install
```

Tables (`collections`, `records`) are created automatically on server start. To initialize them without starting the server:

```bash
npm run db:init
```

## Run

```bash
# Development (watch mode)
npm run dev

# Production
npm run build && npm start
```

Server runs at `http://localhost:4000` by default (override with `PORT` in `.env`).

## API

### Collections (define custom endpoints)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/collections` | Create a new collection (new mock endpoint) |
| GET | `/collections` | List all collections |
| GET | `/collections/:idOrSlug` | Get one collection by id or slug |
| PUT | `/collections/:idOrSlug` | Update collection |
| DELETE | `/collections/:idOrSlug` | Delete collection and its records |

**Create collection body:**

```json
{
  "name": "Users",
  "slug": "users",
  "description": "Mock users",
  "config": { "defaultLimit": 20, "responseDelayMs": 0 }
}
```

- `slug` is used in the URL (e.g. `/mock/users`). Only `a-z`, `0-9`, `-`, `_` allowed.

### Mock data (CRUD per collection)

Base path: **`/mock/:collectionSlug`** (e.g. `/mock/users`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/mock/:collectionSlug` | List records (query: `limit`, `offset`) |
| POST | `/mock/:collectionSlug` | Create a record (body: any JSON) |
| GET | `/mock/:collectionSlug/:id` | Get one record |
| PUT | `/mock/:collectionSlug/:id` | Replace record (full JSON body) |
| PATCH | `/mock/:collectionSlug/:id` | Merge patch into record |
| DELETE | `/mock/:collectionSlug/:id` | Delete record |

List response shape:

```json
{
  "items": [
    {
      "id": "uuid",
      "data": { ... },
      "createdAt": "ISO8601",
      "updatedAt": "ISO8601"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

## Example flow

1. Create a collection:

```bash
curl -X POST http://localhost:4000/collections \
  -H "Content-Type: application/json" \
  -d '{"name":"Users","slug":"users","description":"Mock users"}'
```

2. Add a record:

```bash
curl -X POST http://localhost:4000/mock/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Jane","email":"jane@example.com"}'
```

3. List records:

```bash
curl http://localhost:4000/mock/users?limit=10
```

4. Update by id:

```bash
curl -X PATCH http://localhost:4000/mock/users/<id> \
  -H "Content-Type: application/json" \
  -d '{"name":"Jane Doe"}'
```

5. Delete by id:

```bash
curl -X DELETE http://localhost:4000/mock/users/<id>
```

## Extensibility

- **New endpoints**: Add collections via `POST /collections`; no code changes required.
- **Config**: Each collection has a `config` JSONB field (e.g. `defaultLimit`, `responseDelayMs`) for future options (validation, status overrides, etc.).
- **Data**: Record payloads are stored as JSONB; you can add indexes or constraints in Postgres as needed.
