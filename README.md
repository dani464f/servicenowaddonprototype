# ServiceNow ITAM Right-Sizing Add-on MVP (Netlify-ready)

This repository now includes a **working MVP that runs on Netlify**:

- Static web app UI (`public/index.html`) for:
  - telemetry batch submission
  - policy creation
  - simulation execution
  - recommendation table rendering
- Serverless API (`netlify/functions/api.js`) implementing:
  - `POST /api/v1/ingestion/telemetry-batch`
  - `POST /api/v1/admin/policies`
  - `GET/PATCH /api/v1/admin/policies/{policy_id}`
  - `POST /api/v1/admin/policies/{policy_id}/simulate`
  - `GET /api/v1/recommendations`
  - `GET /api/v1/recommendations/{recommendation_id}`
  - `POST /api/v1/recommendations/{recommendation_id}/approve`
  - `POST /api/v1/recommendations/{recommendation_id}/override`
- Rules/scoring engine (`src/scoring.js`) aligned to blueprint formulas.

## Why Netlify now works

- Added `netlify.toml` with:
  - publish directory set to `public`
  - functions directory set to `netlify/functions`
  - `/api/*` redirect to `/.netlify/functions/api/*`

This ensures both the frontend and backend endpoints are accessible after deploy.

## Local run

```bash
npm install
npx netlify dev
```

Open the local URL shown by Netlify CLI.

## Test

```bash
npm test
```

## Notes

- Storage is in-memory inside the function runtime (MVP behavior).
- For production persistence, replace in-memory maps with PostgreSQL + queue/object storage per blueprint.
