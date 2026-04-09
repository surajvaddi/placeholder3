# Seed Schema And Incremental Run Model

## Objective

Define an updateable seed system for both shots of the pipeline, including a run mode that processes only newly added or modified seeds.

This document covers:

- seed file structure,
- seed identity and versioning,
- how Shot 1 and Shot 2 consume seeds,
- how incremental runs decide what to process,
- what persistence is needed to support this cleanly.

## Design Goals

The seed system should be:

- editable by hand,
- structured enough to drive connector selection,
- stable enough to support incremental processing,
- explicit enough to audit what changed between runs.

## Core Principle

The system should not treat seeds as anonymous strings.

Every seed must have:

- a stable `seed_id`,
- a `seed_kind`,
- a canonical payload,
- an `updated_at` timestamp,
- an `enabled` flag,
- enough metadata to route discovery.

Without stable seed identity, the pipeline cannot reliably run on only new or updated seeds.

## Seed Families

Use two seed families:

1. `parent_seeds`
2. `expansion_seeds`

### Parent seeds

These drive Shot 1.

They describe known umbrella organizations, conferences, circuits, and other top-level discovery anchors.

### Expansion seeds

These drive Shot 2.

They do not represent organizations directly. They represent discovery instructions for how to expand from a parent entity into campus-level records.

This separation matters:

- Shot 1 answers: what parent entities should exist?
- Shot 2 answers: where and how should we look for campus-level entities?

## File Layout

Use a dedicated seed directory:

```text
backend/app/seeds/
  parent_seeds.yaml
  expansion_seeds.yaml
```

Later, optional user-provided seed packs can be merged into this model, but the default repo-owned files should stay simple and canonical.

## Parent Seed Schema

Recommended YAML shape:

```yaml
version: 1
parent_seeds:
  - seed_id: parent_nsbe
    name: National Society of Black Engineers
    category: intercollegiate_organizations
    seed_type: national_org
    aliases:
      - NSBE
    enabled: true
    priority: 10
    source_hints:
      - official_directory
      - wikipedia_reference
    tags:
      - engineering
      - chapters
    notes: strong seed with known chapter model
    updated_at: 2026-04-09

  - seed_id: parent_big_ten
    name: Big Ten Conference
    category: conferences
    seed_type: conference
    aliases:
      - B1G
    enabled: true
    priority: 10
    source_hints:
      - official_members_page
    tags:
      - athletics
    notes: conference member expansion source
    updated_at: 2026-04-09
```

### Parent seed fields

- `seed_id`: stable unique identifier. Never auto-derived at runtime.
- `name`: display name of the seed.
- `category`: business category for downstream labeling.
- `seed_type`: routing hint such as `national_org`, `conference`, `competition`, `network`.
- `aliases`: alternate labels used for matching and normalization.
- `enabled`: whether the seed is active.
- `priority`: optional ordering hint.
- `source_hints`: hints for connector selection.
- `tags`: optional freeform labels.
- `notes`: human-maintained context.
- `updated_at`: change marker controlled by the seed editor.

## Expansion Seed Schema

Recommended YAML shape:

```yaml
version: 1
expansion_seeds:
  - seed_id: expand_official_campus_directory
    connector: campus_directory
    applies_to:
      categories:
        - intercollegiate_organizations
        - cultural_clubs_and_organizations
      seed_types:
        - national_org
    enabled: true
    priority: 10
    discovery_mode: official_directory_only
    host_patterns:
      - "*.edu"
    source_hints:
      - student_org_directory
    limits:
      max_requests_per_parent: 10
      max_results_per_parent: 100
    notes: primary directory expansion path
    updated_at: 2026-04-09

  - seed_id: expand_conference_members
    connector: parent_membership_page
    applies_to:
      categories:
        - conferences
      seed_types:
        - conference
    enabled: true
    priority: 10
    discovery_mode: official_member_pages
    host_patterns:
      - "*.org"
      - "*.com"
    source_hints:
      - official_members_page
    limits:
      max_requests_per_parent: 5
      max_results_per_parent: 200
    notes: use official conference membership pages to discover schools
    updated_at: 2026-04-09
```

### Expansion seed fields

- `seed_id`: stable unique identifier.
- `connector`: connector name to invoke.
- `applies_to`: matching rules for which parent entities this seed can expand.
- `enabled`: whether the rule is active.
- `priority`: ordering hint when multiple rules match.
- `discovery_mode`: connector-specific mode with constrained semantics.
- `host_patterns`: expected source hosts.
- `source_hints`: extra routing hints.
- `limits`: per-parent operational caps.
- `notes`: human-maintained context.
- `updated_at`: change marker controlled by the seed editor.

## Seed Identity Rules

`seed_id` is the primary identity key.

Rules:

- `seed_id` must be unique within its family.
- `seed_id` must be stable across edits.
- changing `name`, `aliases`, `connector`, `applies_to`, or limits must not create a new `seed_id`.
- if the semantic purpose of a seed changes completely, create a new `seed_id` and disable the old one.

This gives the system a durable way to compare past and current seed states.

## Seed Fingerprints

To support incremental runs, each seed should produce a deterministic fingerprint.

Fingerprint inputs should include:

- all routing fields,
- all discovery-relevant fields,
- `enabled`,
- `priority`,
- `source_hints`,
- `limits`,
- aliases,
- category,
- connector and `applies_to` fields.

Fingerprint inputs should exclude:

- cosmetic comment changes,
- file ordering,
- whitespace,
- optionally `notes` if notes should not trigger reprocessing.

Recommended rule:

- `notes` should not affect fingerprints
- `updated_at` should not affect fingerprints

That way, operational changes trigger reprocessing, but documentation edits do not.

## Seed Status Model

Track seed state in the database.

Add a `seed_registry` table with:

- `seed_id`
- `seed_family` (`parent` or `expansion`)
- `fingerprint`
- `enabled`
- `last_seen_at`
- `last_processed_run_id`
- `last_processed_fingerprint`
- `status`

Suggested `status` values:

- `active`
- `disabled`
- `superseded`
- `error`

This table should reflect the latest seed files loaded into the system.

## Run Modes

Support three explicit run modes.

### 1. Full run

Process all enabled seeds.

Use when:

- bootstrapping a new environment,
- validating new connector logic,
- rebuilding the full dataset.

### 2. Incremental run

Process only enabled seeds whose fingerprints are new or changed since their last successful processing.

This should be the default operational mode.

### 3. Seed-targeted run

Process only specific seed IDs explicitly requested by the user or API.

Use when:

- debugging,
- validating one source,
- manually replaying a changed seed.

## What “Only Updated/New Seeds” Means

For Shot 1:

- process a parent seed if it is enabled and either:
  - it has never been processed, or
  - its fingerprint changed since last successful processing.

For Shot 2:

- process an expansion seed if it is enabled and either:
  - it has never been processed, or
  - its fingerprint changed since last successful processing.

But Shot 2 also depends on parent entities. So the actual incremental rule must account for parent changes too.

## Shot 2 Incremental Dependency Rules

Shot 2 should run for a given parent entity when any of these are true:

1. the parent seed behind that entity is new,
2. the parent seed fingerprint changed,
3. a matching expansion seed is new,
4. a matching expansion seed fingerprint changed,
5. the parent entity was newly discovered from Shot 1,
6. the parent entity’s canonical identity or source URL changed.

This is the minimum logic needed for a credible incremental pipeline.

## Processing Units

The pipeline should not think only in terms of “runs.” It should think in terms of processing units.

Recommended units:

- Shot 1 processing unit:
  - one `parent_seed`

- Shot 2 processing unit:
  - one tuple of:
    - `parent_entity_identity`
    - `expansion_seed_id`

That means Shot 2 can rerun only the affected combinations instead of rerunning all parents every time one expansion rule changes.

## Parent Entity Identity

To make Shot 2 incremental, parent entities also need stable identity.

Recommended parent entity identity fields:

- `parent_key`
- canonical `name`
- `category`
- normalized `source_url`
- source connector

Use a deterministic `parent_key` built from canonical discovery fields.

If Shot 1 rediscovers the same entity with the same `parent_key`, Shot 2 can decide whether re-expansion is necessary.

## Run Decision Algorithm

At run start:

1. Load current seed files.
2. Normalize and validate seeds.
3. Compute fingerprints.
4. Upsert current seed definitions into `seed_registry`.
5. Build `changed_parent_seed_ids`.
6. Build `changed_expansion_seed_ids`.
7. Resolve enabled processing units.

Processing decisions:

- Full run:
  - all enabled parent seeds
  - all valid Shot 2 parent/expansion combinations

- Incremental run:
  - Shot 1 on changed parent seeds only
  - Shot 2 on:
    - parents produced by changed Shot 1 seeds
    - plus any existing parent entities matched by changed expansion seeds

- Seed-targeted run:
  - process only requested seed IDs and their dependent units

## Data Persistence Needed

The current schema is not enough for seed-aware incremental runs.

Add these tables.

### `seed_registry`

- `seed_id TEXT PRIMARY KEY`
- `seed_family TEXT NOT NULL`
- `fingerprint TEXT NOT NULL`
- `enabled INTEGER NOT NULL`
- `payload_json TEXT NOT NULL`
- `last_seen_at TEXT NOT NULL`
- `last_processed_run_id INTEGER`
- `last_processed_fingerprint TEXT`
- `last_success_at TEXT`
- `status TEXT NOT NULL`

### `parent_entities`

Add:

- `parent_key TEXT`
- `source_seed_id TEXT`
- `source_connector TEXT`
- `fingerprint TEXT`
- `confidence_score REAL`
- `evidence_json TEXT`

### `org_records`

Add:

- `parent_key TEXT`
- `expansion_seed_id TEXT`
- `record_fingerprint TEXT`
- `confidence_score REAL`
- `review_flags_json TEXT`
- `evidence_json TEXT`

### `processing_history`

- `id INTEGER PRIMARY KEY`
- `run_id INTEGER NOT NULL`
- `shot TEXT NOT NULL`
- `unit_key TEXT NOT NULL`
- `seed_id TEXT`
- `expansion_seed_id TEXT`
- `status TEXT NOT NULL`
- `input_fingerprint TEXT NOT NULL`
- `started_at TEXT NOT NULL`
- `completed_at TEXT`
- `error_message TEXT NOT NULL DEFAULT ''`

This table lets the system know what exactly succeeded before.

## Seed Validation Rules

Validate seeds before a run begins.

Parent seed validation:

- `seed_id` required
- `name` required
- `category` required
- `seed_type` required
- aliases unique after normalization

Expansion seed validation:

- `seed_id` required
- `connector` required
- `applies_to` required
- `host_patterns` required for host-bound connectors
- limits must be positive integers

Invalid seeds should not crash the full system. They should be marked invalid, logged, and skipped.

## Recommended Implementation Rules

### Rule 1

Seed files are inputs, not state.

Do not rely on file modification time to decide what changed. Always use normalized fingerprints.

### Rule 2

Incremental runs should be default, but full runs must remain available.

### Rule 3

Disabling a seed should stop future processing, but should not automatically delete historical data.

If deletion behavior is needed later, add a separate reconciliation mode.

### Rule 4

Expansion seeds should be broad enough to reuse, but narrow enough to remain predictable.

Avoid giant “catch-all” expansion rules that apply to everything.

## API Implications

Extend run creation with an explicit mode.

Example request:

```json
{
  "run_name": "incremental-refresh",
  "mode": "incremental",
  "seed_ids": []
}
```

Supported values:

- `full`
- `incremental`
- `seed_targeted`

For `seed_targeted`, `seed_ids` must be provided.

## Example Incremental Scenario

Initial state:

- `parent_nsbe` already processed
- `expand_official_campus_directory` already processed

Change:

- user edits aliases on `parent_nsbe`
- user adds new expansion seed `expand_chapter_pages`

Incremental outcome:

- Shot 1 reruns `parent_nsbe`
- Shot 2 reruns:
  - NSBE x `expand_official_campus_directory`
  - NSBE x `expand_chapter_pages`
- no unrelated conference or debate seeds rerun

## Recommended First Build Order

1. Replace the current flat seed YAML with structured `parent_seeds.yaml`.
2. Add `expansion_seeds.yaml`.
3. Add seed parsing and validation models.
4. Add fingerprint generation.
5. Add `seed_registry` persistence.
6. Add run modes.
7. Refactor pipeline decision-making around processing units.

## Decisions

These decisions are recommended unless we find a clear reason to change them:

- use separate files for parent and expansion seeds
- require stable human-defined `seed_id`
- use fingerprint-based change detection
- default to incremental runs
- make Shot 2 incremental over parent/expansion pairs, not globally
- treat seed edits as inputs to reprocessing, not immediate destructive sync
