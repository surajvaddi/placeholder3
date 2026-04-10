from __future__ import annotations

import hashlib
import json
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .connectors import build_connector_registry
from .connectors.base import ConnectorContext
from .dedupe import DedupeEngine
from .models import OrgRecord, ParentEntity, RunMode
from .models_seeds import ExpansionSeed, ParentSeed, SeedFamily, SeedRegistryEntry
from .models_sources import OrgRecordCandidate, ParentEntityCandidate
from .services.acceptance import evaluate_org_candidate
from .services.confidence import score_org_candidate, score_parent_candidate
from .services.fetcher import Fetcher
from .services.normalizer import canonical_instagram, normalize_city, normalize_name, normalize_state
from .services.policy import default_policy_registry
from .services.provenance import format_notes_from_evidence
from .services.seeds import SeedService
from .storage import Storage


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_hash(payload: Dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class ShotOneUnit:
    seed: ParentSeed
    unit_key: str
    fingerprint: str


@dataclass
class ShotTwoUnit:
    parent_seed: ParentSeed
    expansion_seed: ExpansionSeed
    parent_entity: ParentEntity
    unit_key: str
    fingerprint: str


class TwoShotPipeline:
    def __init__(
        self, storage: Storage, parent_seed_file: Path, expansion_seed_file: Path
    ):
        self.storage = storage
        self.seed_service = SeedService(
            parent_seed_file=parent_seed_file, expansion_seed_file=expansion_seed_file
        )
        self.dedupe = DedupeEngine()
        self.connectors = build_connector_registry()
        self.policy_registry = default_policy_registry()

    def run(self, run_id: int, mode: RunMode, seed_ids=None) -> Dict:
        requested_seed_ids = {seed_id.lower() for seed_id in (seed_ids or [])}
        self.storage.update_run_status(run_id, status="running")

        bundle = self.seed_service.load_bundle()
        prior_registry_entries = {
            (entry.seed_id, entry.seed_family): entry
            for entry in self.storage.get_seed_registry_entries()
        }
        current_registry_entries = self.seed_service.build_registry_entries(bundle)
        self.storage.upsert_seed_registry_entries(current_registry_entries)

        changed_parent_seeds = self.seed_service.changed_parent_seeds(
            bundle=bundle,
            registry_entries=prior_registry_entries,
            mode=mode.value,
            requested_seed_ids=requested_seed_ids,
        )
        changed_expansion_seeds = self.seed_service.changed_expansion_seeds(
            bundle=bundle,
            registry_entries=prior_registry_entries,
            mode=mode.value,
            requested_seed_ids=requested_seed_ids,
        )

        shot_one_units = self._build_shot_one_units(changed_parent_seeds)
        processed_parents = self._process_shot_one_units(run_id, shot_one_units)
        self.storage.update_run_status(
            run_id, status="running", parent_entity_count=len(processed_parents)
        )

        shot_two_units = self._build_shot_two_units(
            mode=mode,
            bundle=bundle,
            changed_parent_seeds=changed_parent_seeds,
            changed_expansion_seeds=changed_expansion_seeds,
            requested_seed_ids=requested_seed_ids,
        )
        discovered = self._process_shot_two_units(run_id, shot_two_units)
        self.storage.update_run_status(
            run_id, status="running", discovered_club_count=len(discovered)
        )

        deduped = self.dedupe.run(discovered)
        self.storage.replace_org_records(run_id, deduped.records)
        self._mark_parent_seeds_processed(run_id, current_registry_entries, changed_parent_seeds)
        self._mark_expansion_seeds_processed(
            run_id, current_registry_entries, {unit.expansion_seed.seed_id for unit in shot_two_units}
        )
        self.storage.update_run_status(
            run_id, status="completed", deduped_count=len(deduped.records)
        )

        return {
            "parent_entity_count": len(processed_parents),
            "discovered_club_count": len(discovered),
            "deduped_count": len(deduped.records),
            "dedupe_pairs_removed": len(deduped.removed_pairs),
            "processed_parent_seed_ids": [unit.seed.seed_id for unit in shot_one_units],
            "processed_shot_two_unit_keys": [unit.unit_key for unit in shot_two_units],
            "changed_expansion_seed_ids": sorted(
                {unit.expansion_seed.seed_id for unit in shot_two_units}
            ),
        }

    def _build_shot_one_units(self, parent_seeds: List[ParentSeed]) -> List[ShotOneUnit]:
        units: List[ShotOneUnit] = []
        for seed in parent_seeds:
            units.append(
                ShotOneUnit(
                    seed=seed,
                    unit_key=f"parent_seed:{seed.seed_id}",
                    fingerprint=self.seed_service.fingerprint_parent_seed(seed),
                )
            )
        return units

    def _process_shot_one_units(
        self, run_id: int, units: List[ShotOneUnit]
    ) -> List[ParentEntity]:
        started_at = _utc_now()
        entities: List[ParentEntity] = []
        for unit in units:
            entity = asyncio.run(self._run_shot_one_connector(run_id, unit))
            entities.append(entity)
            self.storage.record_processing_history(
                run_id=run_id,
                shot="shot1",
                unit_key=unit.unit_key,
                seed_id=unit.seed.seed_id,
                expansion_seed_id="",
                status="completed",
                input_fingerprint=unit.fingerprint,
                started_at=started_at,
                completed_at=_utc_now(),
                context={"parent_key": entity.parent_key},
            )

        self.storage.save_parent_entities(run_id, entities)
        return entities

    def _build_shot_two_units(
        self,
        mode: RunMode,
        bundle,
        changed_parent_seeds: List[ParentSeed],
        changed_expansion_seeds: List[ExpansionSeed],
        requested_seed_ids: Set[str],
    ) -> List[ShotTwoUnit]:
        enabled_parent_seeds = [seed for seed in bundle.parent_seeds if seed.enabled]
        enabled_expansion_seeds = [seed for seed in bundle.expansion_seeds if seed.enabled]
        changed_parent_ids = {seed.seed_id for seed in changed_parent_seeds}
        changed_expansion_ids = {seed.seed_id for seed in changed_expansion_seeds}
        prior_completed = self.storage.get_successful_processing_fingerprints("shot2")

        units: List[ShotTwoUnit] = []
        for parent_seed in enabled_parent_seeds:
            parent_entity = self._build_parent_entity(parent_seed)
            parent_fingerprint = self.seed_service.fingerprint_parent_seed(parent_seed)

            for expansion_seed in enabled_expansion_seeds:
                if not self._expansion_applies_to_parent(expansion_seed, parent_seed):
                    continue
                if mode == RunMode.seed_targeted and not (
                    parent_seed.seed_id.lower() in requested_seed_ids
                    or expansion_seed.seed_id.lower() in requested_seed_ids
                ):
                    continue
                if (
                    mode == RunMode.seed_targeted
                    and parent_seed.seed_id.lower() in requested_seed_ids
                    and expansion_seed.seed_id.lower() not in requested_seed_ids
                    and any(seed_id.startswith("expand_") for seed_id in requested_seed_ids)
                ):
                    continue

                unit_key = f"{parent_entity.parent_key}::{expansion_seed.seed_id}"
                fingerprint = _stable_hash(
                    {
                        "parent_seed": parent_fingerprint,
                        "expansion_seed": self.seed_service.fingerprint_expansion_seed(
                            expansion_seed
                        ),
                    }
                )
                should_run = mode == RunMode.full
                if mode == RunMode.incremental:
                    should_run = (
                        parent_seed.seed_id in changed_parent_ids
                        or expansion_seed.seed_id in changed_expansion_ids
                        or prior_completed.get(unit_key) != fingerprint
                    )
                if mode == RunMode.seed_targeted:
                    should_run = True
                if not should_run:
                    continue

                units.append(
                    ShotTwoUnit(
                        parent_seed=parent_seed,
                        expansion_seed=expansion_seed,
                        parent_entity=parent_entity,
                        unit_key=unit_key,
                        fingerprint=fingerprint,
                    )
                )

        return units

    def _process_shot_two_units(
        self, run_id: int, units: List[ShotTwoUnit]
    ) -> List[OrgRecord]:
        started_at = _utc_now()
        discovered: List[OrgRecord] = []
        for unit in units:
            records, rejected_count = asyncio.run(self._run_shot_two_connector(run_id, unit))
            discovered.extend(records)
            self.storage.record_processing_history(
                run_id=run_id,
                shot="shot2",
                unit_key=unit.unit_key,
                seed_id=unit.parent_seed.seed_id,
                expansion_seed_id=unit.expansion_seed.seed_id,
                status="completed",
                input_fingerprint=unit.fingerprint,
                started_at=started_at,
                completed_at=_utc_now(),
                context={
                    "parent_key": unit.parent_entity.parent_key,
                    "parent_name": unit.parent_entity.name,
                    "connector": unit.expansion_seed.connector,
                    "record_count": len(records),
                    "rejected_count": rejected_count,
                },
            )
        return discovered

    def _build_parent_entity(self, seed: ParentSeed) -> ParentEntity:
        parent_key = self._build_parent_key(seed)
        return ParentEntity(
            parent_key=parent_key,
            name=seed.name,
            category=seed.category,
            seed_type=seed.seed_type,
            source_seed_id=seed.seed_id,
            source_url=seed.source_url or None,
            notes=f"seeded parent entity; seed_id={seed.seed_id}; seed_type={seed.seed_type}",
        )

    def _build_parent_key(self, seed: ParentSeed) -> str:
        digest = _stable_hash(
            {
                "name": seed.name.lower(),
                "category": seed.category.lower(),
                "seed_type": seed.seed_type.lower(),
                "seed_id": seed.seed_id.lower(),
            }
        )[:16]
        return f"parent_{digest}"

    def _expansion_applies_to_parent(
        self, expansion_seed: ExpansionSeed, parent_seed: ParentSeed
    ) -> bool:
        applies_to = expansion_seed.applies_to
        if applies_to.categories and parent_seed.category not in applies_to.categories:
            return False
        if applies_to.seed_types and parent_seed.seed_type not in applies_to.seed_types:
            return False
        if applies_to.seed_ids and parent_seed.seed_id not in applies_to.seed_ids:
            return False
        if applies_to.tags and not set(parent_seed.tags).intersection(applies_to.tags):
            return False
        return True

    def _mark_parent_seeds_processed(
        self,
        run_id: int,
        registry_entries: List[SeedRegistryEntry],
        seeds: List[ParentSeed],
    ) -> None:
        processed_at = _utc_now()
        selected_seed_ids = {seed.seed_id for seed in seeds}
        for entry in registry_entries:
            if entry.seed_family != SeedFamily.parent:
                continue
            if entry.seed_id not in selected_seed_ids:
                continue
            self.storage.mark_seed_processed(
                run_id=run_id,
                seed_id=entry.seed_id,
                seed_family=entry.seed_family,
                fingerprint=entry.fingerprint,
                processed_at=processed_at,
            )

    def _mark_expansion_seeds_processed(
        self,
        run_id: int,
        registry_entries: List[SeedRegistryEntry],
        seed_ids: Set[str],
    ) -> None:
        processed_at = _utc_now()
        for entry in registry_entries:
            if entry.seed_family != SeedFamily.expansion:
                continue
            if entry.seed_id not in seed_ids:
                continue
            self.storage.mark_seed_processed(
                run_id=run_id,
                seed_id=entry.seed_id,
                seed_family=entry.seed_family,
                fingerprint=entry.fingerprint,
                processed_at=processed_at,
            )

    async def _run_shot_one_connector(self, run_id: int, unit: ShotOneUnit) -> ParentEntity:
        connector_name = self._shot_one_connector_name(unit.seed)
        connector = self.connectors[connector_name]
        async with Fetcher(
            policy_registry=self.policy_registry, connector_name=connector.connector_name
        ) as fetcher:
            candidates = await connector.discover_parent_entities(
                seed=unit.seed,
                fetcher=fetcher,
                context=ConnectorContext(run_id=run_id),
            )
        if not candidates:
            return self._build_parent_entity(unit.seed)
        return self._candidate_to_parent_entity(unit.seed, candidates[0])

    async def _run_shot_two_connector(
        self, run_id: int, unit: ShotTwoUnit
    ) -> Tuple[List[OrgRecord], int]:
        connector = self.connectors[unit.expansion_seed.connector]
        async with Fetcher(
            policy_registry=self.policy_registry, connector_name=connector.connector_name
        ) as fetcher:
            candidates = await connector.discover_org_records(
                parent=unit.parent_entity,
                expansion_seed=unit.expansion_seed,
                fetcher=fetcher,
                context=ConnectorContext(run_id=run_id),
            )
        accepted: List[OrgRecord] = []
        rejected_count = 0
        for candidate in candidates:
            decision = evaluate_org_candidate(candidate)
            if decision.outcome == "rejected":
                rejected_count += 1
                continue
            candidate.review_flags = decision.review_flags
            accepted.append(self._candidate_to_org_record(candidate, decision.outcome))
        return accepted, rejected_count

    def _candidate_to_parent_entity(
        self, seed: ParentSeed, candidate: ParentEntityCandidate
    ) -> ParentEntity:
        parent_key = candidate.parent_key or self._build_parent_key(seed)
        confidence_score, _ = score_parent_candidate(candidate)
        return ParentEntity(
            parent_key=parent_key,
            name=normalize_name(candidate.name),
            category=candidate.category,
            seed_type=candidate.seed_type or seed.seed_type,
            source_seed_id=candidate.source_seed_id or seed.seed_id,
            confidence_score=confidence_score,
            evidence_json=json.dumps([item.model_dump() for item in candidate.evidence], sort_keys=True),
            source_url=candidate.source_url or None,
            notes=format_notes_from_evidence(
                candidate.evidence,
                [candidate.notes, f"confidence={confidence_score:.1f}"],
            ),
        )

    def _shot_one_connector_name(self, seed: ParentSeed) -> str:
        if "sacnas_official_directory" in seed.source_hints:
            return "sacnas_parent_directory"
        if seed.source_url:
            return "official_seed_page"
        return "mock_parent_directory"

    def _candidate_to_org_record(
        self, candidate: OrgRecordCandidate, acceptance_outcome: str
    ) -> OrgRecord:
        confidence_score, confidence_reasons = score_org_candidate(candidate)
        merged_flags = sorted({flag.value for flag in candidate.review_flags})
        return OrgRecord(
            parent_key=candidate.parent_key,
            expansion_seed_id=candidate.expansion_seed_id,
            email=candidate.email,
            name=normalize_name(candidate.name),
            business_name=normalize_name(candidate.business_name),
            category=candidate.category,
            location=candidate.location,
            city=normalize_city(candidate.city),
            state=normalize_state(candidate.state),
            followers=candidate.followers,
            website=candidate.website,
            instagram=canonical_instagram(candidate.instagram),
            confidence_score=confidence_score,
            review_flags_json=json.dumps(merged_flags, sort_keys=True),
            evidence_json=json.dumps([item.model_dump() for item in candidate.evidence], sort_keys=True),
            source_count=len(candidate.evidence),
            notes=format_notes_from_evidence(
                candidate.evidence,
                [
                    candidate.notes,
                    f"confidence={confidence_score:.1f}",
                    f"acceptance={acceptance_outcome}",
                    f"flags={','.join(merged_flags)}" if merged_flags else "",
                    (
                        f"confidence_reasons={','.join(confidence_reasons)}"
                        if confidence_reasons
                        else ""
                    ),
                ],
            ),
        )
