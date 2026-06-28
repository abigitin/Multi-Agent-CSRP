# AgenticAI Customer Support Resolution Platform

## Overview

AgenticAI is a FastAPI + React support-operations app that:

1. Syncs or loads support tickets.
2. Retrieves knowledge from Pinecone or local fallback documents.
3. Generates a human-editable customer email draft.
4. Requires human approval before sending.
5. Sends the approved email through Gmail SMTP and CCs the signed-in reviewer.
6. Protects app access with Google sign-in plus admin approval workflow.

## Deployment Shape

- Frontend: Netlify or Render Static Site
- Backend: Render Web Service
- Database: Neon PostgreSQL

This repo is now prepared for that setup:

- backend uses `DATABASE_URL`
- Postgres driver is declared in `backend/requirements.txt`
- CORS is controlled by `CORS_ORIGINS`
- production boot validation no longer requires unrelated optional integrations
- Render blueprint is included in [render.yaml](/C:/1work/AgenticAI/render.yaml)

## Required Environment Variables

Use [.env.example](/C:/1work/AgenticAI/.env.example) as the template.

Minimum backend variables for deployment:

- `APP_ENV=production`
- `DATABASE_URL=postgresql+psycopg://...`
- `CORS_ORIGINS=https://your-frontend-domain`
- `GOOGLE_CLIENT_ID=...`
- `APP_JWT_SECRET=...`
- `NOTIFICATION_MODE=smtp`
- `MAIL_FROM=...`
- `SMTP_USERNAME=...`
- `SMTP_PASSWORD=...`

Frontend variables:

- `VITE_API_BASE_URL=https://your-render-backend.onrender.com`
- `VITE_GOOGLE_CLIENT_ID=your-google-client-id`

## Deploy Backend On Render

1. Push this repo to GitHub.
2. In Render, create a new Blueprint or Web Service from the repo.
3. If using the included blueprint, Render will read [render.yaml](/C:/1work/AgenticAI/render.yaml).
4. Set these secret env vars in Render:
   - `DATABASE_URL`
   - `CORS_ORIGINS`
   - `GOOGLE_CLIENT_ID`
   - `APP_JWT_SECRET`
   - `MAIL_FROM`
   - `SMTP_USERNAME`
   - `SMTP_PASSWORD`
   - optionally `GROQ_API_KEY`, `PINECONE_API_KEY`, `PINECONE_HOST`
5. Render start command is already defined as:

```text
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Health endpoint:

```text
/health
```

## Deploy Frontend On Netlify

Netlify settings:

- Base directory: `frontend`
- Build command: `npm run build`
- Publish directory: `dist`

Frontend env vars:

```text
VITE_API_BASE_URL=https://your-render-backend.onrender.com
VITE_GOOGLE_CLIENT_ID=your-google-client-id
```

If you prefer Render Static Site instead of Netlify:

- Root directory: `frontend`
- Build command: `npm install && npm run build`
- Publish directory: `dist`

## Neon PostgreSQL

The app supports Neon through a standard SQLAlchemy Postgres URL, for example:

```text
postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

SQLite-specific auto-column migration only runs for SQLite. Postgres uses normal table creation on startup.

## Local Development

Backend:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev -- --port 5173 --strictPort
```

## Notes

- Do not commit `.env` with live secrets.
- Google OAuth must allow your frontend origin.
- Approved email delivery now CCs the signed-in reviewer automatically.
- ServiceNow and Atlassian remain optional; the app can still run with mock/local fallback data.
