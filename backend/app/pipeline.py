import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .dedupe import DedupeEngine
from .models import OrgRecord, ParentEntity, RunMode
from .models_seeds import ExpansionSeed, ParentSeed, SeedFamily, SeedRegistryEntry
from .services.seeds import SeedService
from .storage import Storage


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_hash(payload: dict) -> str:
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

    def run(self, run_id: int, mode: RunMode, seed_ids: list[str] | None = None) -> dict:
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

    def _build_shot_one_units(self, parent_seeds: list[ParentSeed]) -> list[ShotOneUnit]:
        units: list[ShotOneUnit] = []
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
        self, run_id: int, units: list[ShotOneUnit]
    ) -> list[ParentEntity]:
        started_at = _utc_now()
        entities: list[ParentEntity] = []
        for unit in units:
            entity = self._build_parent_entity(unit.seed)
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
        changed_parent_seeds: list[ParentSeed],
        changed_expansion_seeds: list[ExpansionSeed],
        requested_seed_ids: set[str],
    ) -> list[ShotTwoUnit]:
        enabled_parent_seeds = [seed for seed in bundle.parent_seeds if seed.enabled]
        enabled_expansion_seeds = [seed for seed in bundle.expansion_seeds if seed.enabled]
        changed_parent_ids = {seed.seed_id for seed in changed_parent_seeds}
        changed_expansion_ids = {seed.seed_id for seed in changed_expansion_seeds}
        prior_completed = self.storage.get_successful_processing_fingerprints("shot2")

        units: list[ShotTwoUnit] = []
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
        self, run_id: int, units: list[ShotTwoUnit]
    ) -> list[OrgRecord]:
        started_at = _utc_now()
        discovered: list[OrgRecord] = []
        for unit in units:
            records = self._mock_expand_unit(unit)
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
            notes=f"seeded parent entity; seed_id={seed.seed_id}; seed_type={seed.seed_type}",
        )

    def _mock_expand_unit(self, unit: ShotTwoUnit) -> list[OrgRecord]:
        records: list[OrgRecord] = []
        demo_schools = [("Austin", "TX"), ("Los Angeles", "CA"), ("Madison", "WI")]
        slug = unit.parent_entity.name.lower().replace(" ", "")
        for city, state in demo_schools:
            club_name = f"{unit.parent_entity.name} - {city} Chapter"
            records.append(
                OrgRecord(
                    parent_key=unit.parent_entity.parent_key,
                    expansion_seed_id=unit.expansion_seed.seed_id,
                    email=f"contact@{slug}.{state.lower()}.edu",
                    name=club_name,
                    business_name=club_name,
                    category=unit.parent_entity.category,
                    location=f"{city}, {state}",
                    city=city,
                    state=state,
                    followers="",
                    website="",
                    instagram=f"https://instagram.com/{slug}_{city.lower().replace(' ', '')}",
                    notes=(
                        "demo generated record; "
                        f"expansion_seed_id={unit.expansion_seed.seed_id}; "
                        f"connector={unit.expansion_seed.connector}"
                    ),
                )
            )
            records.append(
                OrgRecord(
                    parent_key=unit.parent_entity.parent_key,
                    expansion_seed_id=unit.expansion_seed.seed_id,
                    email="",
                    name=club_name,
                    business_name=f"{unit.parent_entity.name} {city} Chapter",
                    category=unit.parent_entity.category,
                    location=f"{city}, {state}",
                    city=city,
                    state=state,
                    followers="",
                    website="",
                    instagram=f"@{slug}_{city.lower().replace(' ', '')}",
                    notes="possible duplicate variant",
                )
            )
        return records

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
        registry_entries: list[SeedRegistryEntry],
        seeds: list[ParentSeed],
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
        registry_entries: list[SeedRegistryEntry],
        seed_ids: set[str],
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
