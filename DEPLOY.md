# Deploy Max (Render API + Vercel web)

## Why Render for the API

The FastAPI app runs **APScheduler** (SMS reminders, coaching). That needs an **always-on** process.  
Render **free** web services **spin down** when idle → scheduler stops until something hits the API.  
Use at least **Starter** on Render (or any paid/always-on tier) for production.

## 1. Deploy backend (Render)

1. Push this repo to GitHub/GitLab/Bitbucket.
2. [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
3. Connect the repo; Render reads [`render.yaml`](./render.yaml).
4. In the **maxapp-api** service → **Environment**, add every variable from `backend/.env` (Supabase, JWT, Gemini, Stripe, Twilio, AWS, etc.).
5. Set at least:
   - `DEBUG=false`
   - `APP_ENV=production`
   - `CORS_ORIGINS` — comma-separated origins that may call the API, **including your Vercel URL**, e.g.  
     `https://your-app.vercel.app,https://www.yourdomain.com`
6. Deploy. Note the public URL, e.g. `https://maxapp-api.onrender.com`.

**Health check:** `GET https://<your-service>/health`

### Supabase: `MaxClientsInSessionMode` / max pool size

Supabase’s **Session** pooler (port **5432**) allows very few simultaneous clients. On Render, set:

1. **Prefer Transaction pooler:** In Supabase → **Project Settings** → **Database** → **Connection string** → choose **Transaction** (port **6543**). In Render set **`SUPABASE_DB_PORT=6543`** (same host/user/password as before). The app disables asyncpg’s statement cache on 6543 automatically.
2. **Tighten pool (optional):** `SUPABASE_DB_POOL_SIZE=1`, `SUPABASE_DB_MAX_OVERFLOW=0` (defaults in code are already conservative).

Do **not** point multiple deployed APIs at the same Session pooler with large pools.

**Uploads:** `backend/uploads` on Render is ephemeral. Production should use **S3** (already supported in config).

## 2. Deploy Expo web (Vercel)

1. [Vercel](https://vercel.com) → **Add New Project** → import the same repo.
2. **Root Directory:** `mobile`
3. Framework: **Other** (or leave auto-detect; `vercel.json` sets build/output).
4. **Environment variables** (Production — required at **build** time for Expo):
   - `EXPO_PUBLIC_API_BASE_URL` = `https://<your-render-host>/api/`  
     (keep the trailing slash; must match [`mobile/services/api.ts`](./mobile/services/api.ts).)
   - Add any other `EXPO_PUBLIC_*` keys you use (e.g. Stripe link vars from `PaymentScreen`).
5. Deploy.

Preview deployments: add the same variables for **Preview** or point previews at a staging API.  
Update **Render** `CORS_ORIGINS` to include `https://*.vercel.app` if you use preview URLs.

## 3. Local checks

```bash
cd mobile
npm install
npm run build:web
# output in mobile/dist
```

```bash
# From repo root (same layout as Render)
docker build -t maxapp-api .
docker run -p 8000:8000 --env-file backend/.env -e PORT=8000 maxapp-api
```

(Alternatively: `docker build -f backend/Dockerfile -t maxapp-api backend` uses only the `backend/` folder.)

## Files added

| File | Purpose |
|------|---------|
| `Dockerfile` (repo root) | Production image for Render (`COPY backend/...`) |
| `.dockerignore` (repo root) | Smaller context when building from root |
| `backend/Dockerfile` | Optional: `docker build -f backend/Dockerfile backend` |
| `backend/.dockerignore` | Smaller builds when using backend-only context |
| `render.yaml` | Render Blueprint (web service) |
| `mobile/vercel.json` | Static web export + SPA fallback |
| `mobile/package.json` | `build:web` script |
