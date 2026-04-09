# Collegiate Org Prospecting Platform

A local-first, two-shot prospecting system that builds a high-quality CSV of collegiate organizations for outreach.

## What this repository includes

- Python backend (`FastAPI`) for orchestration, enrichment, deduplication, storage, and CSV export.
- Node.js frontend (`Next.js`) for running jobs, monitoring status, and downloading records.
- Planning and architecture docs in `docs/PLANS.md`.

## Core workflow (two shots)

1. **Shot 1 - Source Parent Entities**
   - Start from seed categories and known umbrella organizations (conference, national body, competition circuit, etc.).
   - Produce a curated list of parent entities relevant to your merchandise niche.

2. **Shot 2 - Expand to College-Level Targets**
   - For each parent entity, discover individual campus clubs/chapters/teams/associations.
   - Enrich each club with contact and social signals.
   - Normalize and deduplicate records before persistence.

## Target output schema

Each final club/chapter record is stored with:

- `email`
- `name`
- `business_name`
- `category`
- `location`
- `city`
- `state`
- `followers`
- `website`
- `instagram`
- `notes`
- `status`

## Quick start

### 1) Backend (Python)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`.

### 2) Frontend (Node.js / Next.js)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`.

### 3) Run a pipeline job

From UI:
- Enter a run name and optional notes.
- Click **Start Two-Shot Run**.
- Wait for completion and download CSV.

From API:

```bash
curl -X POST http://localhost:8000/runs -H "Content-Type: application/json" -d '{"run_name":"initial-run"}'
```

## Important compliance notes

- Respect each source's Terms of Service and robots directives.
- Use low-rate request patterns and explicit source attribution in notes.
- Avoid scraping private or authenticated pages.
- For Instagram specifically, use permitted access patterns (official APIs or compliant public metadata collection policy).

This baseline is intentionally modular so compliant connectors can be swapped in per source.
