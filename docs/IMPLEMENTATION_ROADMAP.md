# Implementation Roadmap

## Objective

Turn the current Milestone 1 baseline into a production-shaped local-first prospecting system in a sequence that is technically sound and easy to validate.

This roadmap integrates:

- the baseline plan in `docs/PLANS.md`
- the scraping architecture in `docs/SCRAPING_ARCHITECTURE.md`
- the seed and incremental run model in `docs/SEED_SCHEMA.md`

The goal is to build the system in dependency order instead of feature order.

## Guiding Rule

Do not start with source-specific scraping logic.

The first work should establish:

1. seed identity and incremental processing
2. connector boundaries
3. shared fetch and policy controls
4. normalization and acceptance layers
5. only then real connectors

If this order is reversed, the codebase will quickly accumulate source-specific logic in the pipeline and storage layers.

## Current Baseline

What already exists:

- FastAPI app
- SQLite storage
- basic run model
- mock two-shot pipeline
- baseline dedupe engine
- minimal Next.js dashboard

What does not exist yet:

- structured seed system
- incremental run model
- connector interfaces
- compliance-aware fetch runtime
- provenance storage
- confidence and acceptance logic
- real source connectors
- review workflow

## Build Phases

Use six phases.

### Phase 0: Align The Data Contract

Objective:

- make the plan, architecture, and seed model internally consistent before coding deeper

Tasks:

1. keep `docs/PLANS.md` as product intent
2. keep `docs/SCRAPING_ARCHITECTURE.md` as source/runtime design
3. keep `docs/SEED_SCHEMA.md` as incremental input design
4. treat this roadmap as the implementation order contract

Exit criteria:

- no major ambiguity about what a seed is
- no ambiguity about how Shot 2 incremental processing works
- no ambiguity about where scraping logic lives

### Phase 1: Seed Foundation

Objective:

- replace the flat seed list with structured seed families and incremental state tracking

Why this phase comes first:

- both the pipeline and the scraping system depend on stable seed identity
- your requirement to run only on new or changed seeds cannot be implemented later as a bolt-on

Tasks:

1. replace `default_seed_categories.yaml` with:
   - `parent_seeds.yaml`
   - `expansion_seeds.yaml`
2. add Pydantic models for:
   - parent seeds
   - expansion seeds
   - run modes
3. add seed loading, validation, and normalization
4. add deterministic seed fingerprinting
5. add `seed_registry` persistence
6. extend run creation API to support:
   - `full`
   - `incremental`
   - `seed_targeted`

Key files to add:

- `backend/app/seeds/parent_seeds.yaml`
- `backend/app/seeds/expansion_seeds.yaml`
- `backend/app/models_seeds.py`
- `backend/app/services/seeds.py`

Schema changes:

- add `seed_registry`

Exit criteria:

- the system can load structured seeds
- the system can determine which seeds are new or changed
- the API can request an incremental run without ambiguity

### Phase 2: Pipeline Refactor

Objective:

- refactor the pipeline around processing units instead of one monolithic run path

Why this phase comes second:

- connector work needs a pipeline that can process parent seeds and parent/expansion pairs cleanly

Tasks:

1. refactor `TwoShotPipeline` into explicit stages:
   - load seed state
   - resolve run units
   - process Shot 1 units
   - process Shot 2 units
   - dedupe
   - persist
2. introduce processing units:
   - Shot 1 unit = `parent_seed_id`
   - Shot 2 unit = `parent_key + expansion_seed_id`
3. add `processing_history`
4. add `parent_key` identity generation
5. keep existing mock behavior behind new interfaces until real connectors are added

Key files to update:

- `backend/app/pipeline.py`
- `backend/app/storage.py`
- `backend/app/models.py`

Schema changes:

- add `processing_history`
- extend `parent_entities`
- extend `org_records`

Exit criteria:

- full and incremental runs produce different processing scopes
- Shot 2 can rerun only affected parent/expansion combinations
- mock connectors can execute through the new stage model

### Phase 3: Connector Spine

Objective:

- introduce the shared abstractions and runtime required for safe real scraping

Why this phase comes third:

- once seeds and pipeline units exist, connectors can be plugged in cleanly

Tasks:

1. add connector interfaces
2. add candidate models:
   - `ParentEntityCandidate`
   - `OrgRecordCandidate`
   - `Evidence`
   - `ReviewFlag`
3. add shared `Fetcher`
4. add deny-by-default `SourcePolicy` registry
5. add normalization helpers
6. add provenance formatting helpers

Key files to add:

- `backend/app/connectors/base.py`
- `backend/app/services/fetcher.py`
- `backend/app/services/policy.py`
- `backend/app/services/normalizer.py`
- `backend/app/services/provenance.py`
- `backend/app/models_sources.py`

Dependencies:

- Phase 1 seed models determine connector routing metadata
- Phase 2 pipeline determines how connector outputs flow through the system

Exit criteria:

- the pipeline can call connectors through a common interface
- all outbound requests must flow through the shared fetcher
- source host access is policy-gated

### Phase 4: Quality Layer

Objective:

- centralize record quality decisions outside connector code

Why this phase comes before real connectors:

- real sources should plug into stable acceptance and scoring rules instead of inventing their own behavior

Tasks:

1. add acceptance outcomes:
   - `accepted`
   - `accepted_with_review`
   - `rejected`
2. add confidence scoring for parent and org candidates
3. add richer dedupe inputs and merge ranking
4. store evidence and review flags in persistence
5. update export note generation to include provenance breadcrumbs

Key files to add:

- `backend/app/services/acceptance.py`
- `backend/app/services/confidence.py`

Key files to update:

- `backend/app/dedupe.py`
- `backend/app/storage.py`

Exit criteria:

- connectors emit candidates, not final records
- the system can score, accept, review-flag, or reject candidates centrally
- final records carry provenance and confidence information

### Phase 5: First Real Connectors

Objective:

- replace the mock discovery path with one small, stable, real slice

Why this phase is intentionally narrow:

- the first real connector should validate the architecture, not maximize source count

Tasks:

1. implement one Shot 1 connector
2. implement one Shot 2 connector
3. run both only through the new connector/fetch/policy path
4. keep Instagram enrichment out unless the policy layer is ready for it
5. write fixture-based tests around parsing and normalization

Recommended first slice:

- Shot 1:
  - one official parent directory or curated source
- Shot 2:
  - one stable public campus directory source with HTML or JSON that does not require JS execution

Exit criteria:

- at least one end-to-end run uses real external data
- the system respects seed-targeted and incremental semantics
- provenance and confidence are persisted

### Phase 6: Operations And Review

Objective:

- make the system practical to operate and inspect

Tasks:

1. add run logs
2. add error diagnostics
3. add review counts and review flags to the API
4. expose record review actions in the UI
5. add worker mode for long runs
6. add scheduling later if needed

Key files to update:

- `backend/app/main.py`
- `frontend/app/page.tsx`
- new review endpoints as needed

Exit criteria:

- long runs are inspectable
- low-confidence records are reviewable
- the UI reflects the real state of the backend

## Dependency Graph

Build order dependency summary:

- Phase 1 blocks everything else
- Phase 2 depends on Phase 1
- Phase 3 depends on Phases 1 and 2
- Phase 4 depends on Phase 3
- Phase 5 depends on Phases 1 through 4
- Phase 6 can begin after Phase 4, but is most valuable after Phase 5

This is the critical-path reasoning:

- seeds define processing scope
- pipeline defines execution structure
- connectors need execution structure
- real connectors need fetch, policy, and quality layers
- review UX is low value until real records and evidence exist

## Testing Strategy By Phase

### Phase 1

- seed parsing tests
- seed validation tests
- fingerprint stability tests

### Phase 2

- incremental run decision tests
- processing unit selection tests
- parent key identity tests

### Phase 3

- fetcher retry and timeout tests
- policy allow/deny tests
- connector contract tests

### Phase 4

- acceptance rule tests
- confidence scoring tests
- dedupe merge ranking tests

### Phase 5

- parser fixture tests
- end-to-end pipeline tests with recorded source fixtures

### Phase 6

- API integration tests
- UI smoke tests for run status and review actions

## Recommended Immediate Next Step

Start with Phase 1.

More specifically:

1. introduce `models_seeds.py`
2. create `parent_seeds.yaml`
3. create `expansion_seeds.yaml`
4. add a seed loader service
5. add fingerprinting
6. add `seed_registry`
7. extend run creation request with `mode`

That gives the whole project a stable input and reprocessing model before deeper refactors begin.

## What Not To Do Yet

Avoid these until the earlier phases are in place:

- adding browser automation
- scraping many sources at once
- building the review UI first
- expanding the CSV schema prematurely
- hardcoding source-specific parsing logic into `pipeline.py`

## Definition Of A Solid Codebase Here

For this project, a solid codebase means:

- inputs are explicit and versionable
- run scope is deterministic
- scraping is policy-gated
- source-specific logic is isolated in connectors
- quality rules are centralized
- evidence is preserved
- reruns are incremental by default
- future sources can be added without redesigning the system
