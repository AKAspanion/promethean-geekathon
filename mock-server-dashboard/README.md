# Mock Server Dashboard

Next.js frontend for managing **collections** and **records** on the [mock-server](../mock-server) backend.

## Features

- **Collections CRUD**: List, create, edit, and delete collections (name, slug, description, config JSON).
- **Records CRUD**: Per collection, list, create, edit (replace), and delete records (JSON data).
- Backend health indicator in the nav (connected / unreachable).

## Setup

1. Ensure the [mock-server](../mock-server) is running (default: `http://localhost:4000`).
2. From this directory:

```bash
npm install
cp .env.example .env   # optional: edit if backend runs on another URL/port
npm run dev
```

The dashboard runs at **http://localhost:5000**.

## Environment

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_MOCK_SERVER_URL` | Backend base URL (default: `http://localhost:4000`) |

## Scripts

- `npm run dev` – Dev server on port **5000**
- `npm run build` – Production build
- `npm run start` – Run production server (use `-p 5000` if you need port 5000)
