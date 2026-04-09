# Scraping Architecture

## Objective

Define a concrete scraping architecture for the two-shot collegiate prospecting platform that is:

- compliant by default,
- deterministic enough for repeatable runs,
- modular enough to add new sources without rewriting the pipeline,
- simple enough to fit the current local-first FastAPI + SQLite codebase.

This document is the implementation contract for replacing the current mock discovery flow.

## Current Constraints

- The backend currently runs the pipeline synchronously inside `POST /runs`.
- Persistence is SQLite.
- `TwoShotPipeline` is the natural orchestration layer.
- There is no existing connector abstraction, fetch layer, provenance model, or review queue.

## Design Overview

The scraping system should be split into five layers:

1. `Pipeline orchestration`
2. `Source connectors`
3. `Fetch/compliance runtime`
4. `Normalization + acceptance`
5. `Persistence + provenance`

The pipeline should never issue raw HTTP requests directly. All external discovery should flow through a connector, and every connector should use the same compliance-aware fetch client.

## Target Package Layout

Add these modules under `backend/app/`:

```text
backend/app/
  connectors/
    __init__.py
    base.py
    parent_directory.py
    campus_directory.py
    social_public.py
  services/
    fetcher.py
    policy.py
    provenance.py
    normalizer.py
    acceptance.py
    confidence.py
  models_sources.py
```

Purpose:

- `connectors/base.py`: shared connector interfaces and result models.
- `connectors/parent_directory.py`: shot 1 discovery from official or curated parent sources.
- `connectors/campus_directory.py`: shot 2 discovery from campus club directories and member pages.
- `connectors/social_public.py`: public social enrichment for already-discovered entities.
- `services/fetcher.py`: shared HTTP client, retries, timeouts, headers, rate limiting.
- `services/policy.py`: robots/TOS allow/deny rules and per-host policy lookup.
- `services/provenance.py`: source breadcrumb formatting and evidence capture.
- `services/normalizer.py`: canonicalization for names, URLs, geography, Instagram handles.
- `services/acceptance.py`: record acceptance and review flagging rules.
- `services/confidence.py`: confidence scoring for parent entities and org records.
- `models_sources.py`: structured evidence, source documents, and review flags.

## Core Runtime Flow

### Shot 1

1. Load seed categories from YAML.
2. Normalize seed labels.
3. For each seed, ask one or more parent-source connectors for candidate parent entities.
4. Score each candidate.
5. Keep candidates above threshold.
6. Store parent entities plus evidence.

### Shot 2

1. For each stored parent entity, choose eligible campus-level connectors.
2. Discover campus clubs/chapters/teams.
3. Normalize org name, school signal, city/state, and public contact fields.
4. Enrich with optional social and website signals.
5. Apply acceptance rules.
6. Mark low-confidence or ambiguous records for review.
7. Deduplicate.
8. Persist final records plus source breadcrumbs.

## Connector Interface

All connectors should implement a common interface.

```python
class BaseConnector(Protocol):
    connector_name: str

    def supports_shot_one(self) -> bool: ...
    def supports_shot_two(self) -> bool: ...

    async def discover_parent_entities(
        self,
        seed_name: str,
        category: str,
        fetcher: Fetcher,
    ) -> list[ParentEntityCandidate]: ...

    async def discover_org_records(
        self,
        parent: ParentEntityCandidate,
        fetcher: Fetcher,
    ) -> list[OrgRecordCandidate]: ...
```

Not every connector has to implement both methods. A connector can raise `NotImplementedError` for unsupported phases.

## Connector Types

Use three connector classes.

### 1. Parent directory connectors

Used in shot 1.

Examples:

- official national organization chapter directories,
- conference member-school directories,
- curated parent source pages.

Output:

- `ParentEntityCandidate`
- category
- canonical name
- source URL
- evidence snippets
- confidence inputs

### 2. Campus directory connectors

Used in shot 2.

Examples:

- university student organization listings,
- club sports pages,
- chapter rosters,
- official team or member pages.

Output:

- `OrgRecordCandidate`
- org name
- school or campus signal
- city/state if available
- public email/website/social fields
- evidence set

### 3. Social enrichment connectors

Used only after a campus entity already exists.

Examples:

- public Instagram handle normalization,
- follower count extraction if policy allows,
- cross-link resolution from website to social.

These should enrich records, not create new records by themselves unless a later policy explicitly allows it.

## Data Models

Introduce structured intermediate models before persistence.

```python
class Evidence(BaseModel):
    connector: str
    source_url: str
    source_type: str
    observed_at: str
    snippet: str = ""
    confidence_note: str = ""


class ReviewFlag(str, Enum):
    ambiguous_name = "ambiguous_name"
    weak_source = "weak_source"
    conflicting_geo = "conflicting_geo"
    social_only = "social_only"


class ParentEntityCandidate(BaseModel):
    name: str
    category: str
    source_url: str = ""
    confidence_score: float = 0.0
    evidence: list[Evidence] = []


class OrgRecordCandidate(BaseModel):
    email: str = ""
    name: str
    business_name: str
    category: str
    location: str = ""
    city: str = ""
    state: str = ""
    followers: str = ""
    website: str = ""
    instagram: str = ""
    confidence_score: float = 0.0
    review_flags: list[ReviewFlag] = []
    evidence: list[Evidence] = []
```

The existing `OrgRecord` can remain the persistence model for export, but it should be built from `OrgRecordCandidate` after normalization, acceptance, and dedupe.

## Fetch Layer

All external requests should go through a shared `Fetcher`.

Responsibilities:

- one `httpx.AsyncClient`,
- global timeouts,
- retry policy for transient failures,
- per-host rate limiting,
- user-agent header,
- optional robots lookup,
- response metadata logging,
- content-type guards,
- request budget tracking per run.

Recommended defaults:

- timeout: `10s connect / 20s read`
- retries: `2`
- backoff: exponential with jitter
- per-host concurrency: `1`
- minimum delay per host: `1-2s`

The fetcher should expose simple methods:

```python
class Fetcher:
    async def get_text(self, url: str, policy_tag: str) -> FetchResult: ...
    async def get_json(self, url: str, policy_tag: str) -> FetchResult: ...
    async def head(self, url: str, policy_tag: str) -> FetchResult: ...
```

`policy_tag` links each request to a source policy entry.

## Policy Layer

Create a host policy registry in code first, then move to config if needed.

Each policy entry should define:

- host pattern,
- allowed connector types,
- robots requirement,
- request delay,
- max pages per run,
- allowed content types,
- notes on terms or restrictions.

Example policy shape:

```python
SourcePolicy(
    host="example.edu",
    robots_required=True,
    min_delay_seconds=1.5,
    max_requests_per_run=25,
    allow_html=True,
    allow_json=False,
    notes="Public organization directory only",
)
```

If no policy matches a host, default to deny. This is safer than implicit allow.

## Parsing Strategy

Keep parsing simple and deterministic.

- Prefer JSON or structured APIs when available.
- Use HTML parsing only for public, stable pages.
- Avoid browser automation in the first implementation.
- Avoid scraping authenticated pages entirely.

Library recommendation for initial implementation:

- `httpx` for network access
- `beautifulsoup4` + `lxml` for HTML parsing

Do not add Playwright or Selenium in the first pass. They add complexity, slow runs, and increase compliance risk. If a source requires JS execution, treat it as unsupported until explicitly approved.

## Normalization Layer

Normalization should happen before acceptance and dedupe.

Responsibilities:

- canonicalize names
- standardize state abbreviations
- normalize city casing
- canonicalize websites
- canonicalize Instagram handles
- normalize school suffixes and abbreviations

Examples:

- `Univ. of Texas` -> `University of Texas`
- `instagram.com/foo/` -> `foo`
- `Madison WI` -> `city=Madison, state=WI`

This layer should also build a cleaner dedupe signature than the current ad hoc logic.

## Acceptance Rules

Create explicit acceptance outcomes:

- `accepted`
- `accepted_with_review`
- `rejected`

Suggested rules:

1. Accept if valid public email exists.
2. Accept if website or Instagram exists and there is a strong campus or school signal.
3. Accept with review if only social evidence exists.
4. Reject if org name is too generic and there is no school linkage.
5. Reject if geography conflicts cannot be resolved.

This logic should be centralized in `services/acceptance.py`, not embedded in connectors.

## Confidence Scoring

Introduce a lightweight score now rather than a perfect model later.

Suggested score inputs:

- `+3` official school or official organization domain
- `+2` public email on official page
- `+2` structured directory listing
- `+1` corroborated by second source
- `-2` social-only evidence
- `-2` ambiguous org naming
- `-3` conflicting geography

Thresholds:

- `>= 5`: accept
- `3-4`: accept with review
- `< 3`: reject

Store the score in persistence and include a short score explanation in `notes`.

## Provenance

Every accepted record should carry machine-readable evidence internally and a human-readable breadcrumb in `notes`.

Internal evidence should be preserved separately from the export string.

Recommended `notes` format:

```text
sources=campus_directory,official_chapter_page; urls=https://... ,https://...; confidence=6; flags=social_only
```

This keeps exports auditable without forcing the CSV schema to change too much.

## Persistence Changes

The current schema is too thin for real scraping. Extend it with:

### `runs`

- `started_at`
- `completed_at`
- `error_message`
- `request_count`

### `parent_entities`

- `confidence_score`
- `evidence_json`
- `status`

### `org_records`

- `confidence_score`
- `review_flags_json`
- `evidence_json`
- `source_count`

### New `run_logs` table

- `id`
- `run_id`
- `stage`
- `level`
- `message`
- `context_json`
- `created_at`

The JSON fields can be stored as text in SQLite.

## Pipeline Refactor

Refactor `TwoShotPipeline` into stage methods that operate on candidates.

```python
run()
  -> collect_parent_candidates()
  -> score_and_store_parents()
  -> discover_org_candidates()
  -> normalize_and_filter_candidates()
  -> dedupe_records()
  -> persist_records()
```

This keeps connector logic separate from record quality decisions.

## Execution Model

Short term:

- keep synchronous API behavior for simplicity,
- use `asyncio.run()` internally or convert the route and pipeline to async,
- run connectors concurrently with bounded concurrency.

Medium term:

- move run execution to a worker,
- keep the exact same connector and fetch interfaces.

The key point is that the scraping architecture should not depend on whether execution is in-request or in-worker.

## Error Handling

Connector failures should degrade gracefully.

- a single source failure should not fail the entire run,
- connector exceptions should be logged into `run_logs`,
- policy denials should be explicit and visible,
- partial results should still dedupe and export.

Only fail the full run when:

- seed loading fails,
- database persistence fails,
- every required connector fails and zero candidates are produced.

## Frontend Implications

The current UI is enough for Milestone 1, but the scraping architecture expects later UI additions:

- run stage progress,
- warnings and review counts,
- failed source diagnostics,
- record review actions,
- evidence visibility per record.

These are not required for the first implementation pass, but the backend should persist the data now so the UI can catch up later.

## Recommended Build Order

Phase 1:

1. Add connector interfaces and source candidate models.
2. Add shared fetcher and policy registry.
3. Add normalization helpers.
4. Refactor pipeline to consume connectors.

Phase 2:

5. Add one real shot 1 connector.
6. Add one real shot 2 connector.
7. Add acceptance and confidence scoring.
8. Persist evidence and review flags.

Phase 3:

9. Harden dedupe with normalized signatures and record quality ranking.
10. Add run logs and failure diagnostics.
11. Expose review state in the UI.

## First Implementation Slice

The first build slice should be intentionally small:

- add the connector base classes,
- add `Fetcher`,
- add `SourcePolicy`,
- add one campus directory connector for a stable public source,
- keep Instagram enrichment out of the first slice,
- keep browser automation out of the first slice.

That gives the project a real scraping spine without committing too early to fragile sources.

## Decisions

These decisions are recommended unless there is a strong reason to change them:

- Use `httpx.AsyncClient`.
- Use a deny-by-default host policy model.
- Prefer HTML + JSON parsing over browser automation.
- Treat social enrichment as secondary, not primary discovery.
- Store structured provenance in SQLite text columns as JSON.
- Keep export schema stable and enrich `notes` rather than expanding CSV immediately.
