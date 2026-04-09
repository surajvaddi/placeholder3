# PLANS: Two-Shot Collegiate Lead Discovery Platform

## 1) Objective

Build a local-first platform that discovers and exports collegiate organizations as outreach-ready prospects for a group merchandise brand.

The system must:

- Run on a laptop.
- Use a Python backend for scraping/orchestration/deduplication/export.
- Use a Node.js frontend for run control and visibility.
- Execute a two-shot pipeline:
  - Shot 1: discover parent entities (national orgs, conferences, circuits).
  - Shot 2: discover individual campus-level organizations.
- Produce a CSV with fields:
  - `email`, `name`, `business_name`, `category`, `location`, `city`, `state`, `followers`, `website`, `instagram`, `notes`, `status`.
- Prioritize quality, thoroughness, and duplicate prevention.

---

## 2) Non-Functional Priorities

- **Accuracy first**: prefer fewer but verified club records vs large noisy lists.
- **Source traceability**: every final record should carry source breadcrumbs in `notes`.
- **Repeatability**: rerunning with the same seeds should generate deterministic outcomes after dedupe.
- **Extensibility**: connector-based architecture for adding new discovery sources.
- **Compliance-aware design**: source-specific fetch limits, robots/TOS checks, and optional API-first connectors.

---

## 3) Architecture (Current Baseline)

### Backend (`backend/`)

- `FastAPI` service.
- `SQLite` storage for runs and records.
- `TwoShotPipeline` orchestrator:
  - `_shot_one_collect_parent_entities()`
  - `_shot_two_expand_to_college_level()`
- `DedupeEngine` using:
  - hard keys (email/website/instagram),
  - signature matching,
  - fuzzy business-name + geography matching.
- CSV export endpoint.

### Frontend (`frontend/`)

- `Next.js` app.
- Dashboard to:
  - create new runs,
  - display run counts,
  - download CSV exports.

---

## 4) Shot 1 Plan (Parent Entity Discovery)

### Seed Inputs

- Curated seed file by category (already scaffolded in `backend/app/seeds/default_seed_categories.yaml`).
- Optional future seed sources:
  - user-uploaded CSV seed packs,
  - external curated datasets,
  - historical high-converting parent entities.

### Discovery Actions

1. Normalize and canonicalize seed names.
2. Resolve each to candidate parent entity pages (official site + references).
3. Validate relevance to collegiate ecosystem.
4. Store parent entities with:
   - category,
   - source URL,
   - confidence notes.

### Parent Confidence Heuristics

- +2 if official domain match found.
- +2 if collegiate keywords present.
- +1 if recurring across >1 trusted source.
- Reject below minimum score.

---

## 5) Shot 2 Plan (Campus-Level Organization Expansion)

For each parent entity:

1. Discover chapter/team/club listings from:
   - official chapter directories,
   - conference member pages,
   - campus organization directories,
   - public social profiles.
2. Extract campus-level entity names.
3. Enrich each with available contact channels:
   - email (if public),
   - website,
   - Instagram handle/URL,
   - optional followers count.
4. Standardize geography (city/state).
5. Save source evidence in `notes` for manual QA.

### Record Acceptance Rules

A campus-level record is accepted if either:

- has valid email, or
- has website or Instagram and includes a credible org name + school/campus link.

### Evidence Strength Tiers

- **Tier A**: official campus directory + email.
- **Tier B**: official club page + social handle.
- **Tier C**: social-only signal with weak corroboration (flag for review).

---

## 6) Deduplication System (Critical)

The dedupe design is layered:

1. **Exact contact keys**
   - identical normalized email
   - identical canonical website domain/path
   - identical canonical Instagram handle
2. **Composite signature**
   - normalized `business_name + city + state + website + instagram`
3. **Fuzzy near-duplicate**
   - token similarity on `business_name`
   - must match state and preferably city
4. **Merge strategy**
   - keep best available field values
   - append note history from merged records

### Planned hardening

- scoring model for “best record” winner
- phonetic and abbreviation normalization (e.g., “Univ” vs “University”)
- campus alias dictionary
- domain reputation allow/deny lists

---

## 7) Data Model and CSV Contract

Final CSV columns and intended semantics:

- `email`: best outreach email if found.
- `name`: human-readable contact/org descriptor.
- `business_name`: normalized org/club/chapter name.
- `category`: source category (club sports, debate, etc.).
- `location`: free-form location string.
- `city`: normalized city.
- `state`: 2-letter or normalized state string.
- `followers`: social followers estimate/string.
- `website`: canonical website URL.
- `instagram`: canonical Instagram URL or handle.
- `notes`: evidence, confidence, and source annotations.
- `status`: workflow marker (`new`, `reviewed`, `contacted`, `do_not_contact`).

---

## 8) Accuracy & QA Process

### Automated checks

- email format validation
- URL normalization and accessibility check (future)
- social handle normalization
- entity/geography sanity checks

### Manual review queue

Flag records for review when:

- conflicting city/state signals
- social-only records with no corroborating source
- ambiguous organization names

---

## 9) Compliance & Risk Controls

- Implement source connector policies:
  - request rate limits per host,
  - robots policy checks where applicable,
  - user-agent identification.
- Prefer official/public APIs where available.
- Keep scraping scope to publicly available organizational contact data.
- Record source provenance in `notes` to support audits.

---

## 10) Milestones

### Milestone 1 (Completed in this baseline)

- Backend API scaffold
- Two-shot orchestrator skeleton
- Storage + CSV export
- Baseline dedupe engine
- Frontend dashboard to run and export

### Milestone 2

- Implement real connectors for:
  - parent directory sources
  - campus org listings
  - Instagram enrichment workflow
- Add per-source confidence scoring.

### Milestone 3

- Add queue worker mode for long runs.
- Add run logs and error diagnostics in UI.
- Add human-in-the-loop review actions.

### Milestone 4

- Add scheduling and incremental refresh.
- Add conversion tracking feedback loop to prioritize high-yield categories.

---

## 11) Immediate Next Steps

1. Replace mock Shot 2 generator with real source connectors.
2. Add explicit confidence score field and threshold filtering.
3. Add unit tests for dedupe merge behavior.
4. Add upload endpoint for custom seed lists.
5. Add “reviewed/contacted” UI actions per record.
