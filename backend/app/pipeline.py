from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .dedupe import DedupeEngine
from .models import OrgRecord, ParentEntity, RunMode
from .models_seeds import ParentSeed, SeedFamily, SeedRegistryEntry
from .services.seeds import SeedService
from .storage import Storage


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
        registry_entries = {
            (entry.seed_id, entry.seed_family): entry
            for entry in self.storage.get_seed_registry_entries()
        }
        current_registry_entries = self.seed_service.build_registry_entries(bundle)
        self.storage.upsert_seed_registry_entries(current_registry_entries)

        parent_seeds = self.seed_service.changed_parent_seeds(
            bundle=bundle,
            registry_entries=registry_entries,
            mode=mode.value,
            requested_seed_ids=requested_seed_ids,
        )
        expansion_seeds = self.seed_service.changed_expansion_seeds(
            bundle=bundle,
            registry_entries=registry_entries,
            mode=mode.value,
            requested_seed_ids=requested_seed_ids,
        )

        parent_entities = self._shot_one_collect_parent_entities(parent_seeds)
        self.storage.save_parent_entities(run_id, parent_entities)
        self.storage.update_run_status(
            run_id, status="running", parent_entity_count=len(parent_entities)
        )

        discovered = self._shot_two_expand_to_college_level(parent_entities)
        self.storage.update_run_status(
            run_id, status="running", discovered_club_count=len(discovered)
        )

        deduped = self.dedupe.run(discovered)
        self.storage.replace_org_records(run_id, deduped.records)
        self._mark_parent_seeds_processed(run_id, current_registry_entries, parent_seeds)
        self.storage.update_run_status(
            run_id, status="completed", deduped_count=len(deduped.records)
        )

        return {
            "parent_entity_count": len(parent_entities),
            "discovered_club_count": len(discovered),
            "deduped_count": len(deduped.records),
            "dedupe_pairs_removed": len(deduped.removed_pairs),
            "processed_parent_seed_ids": [seed.seed_id for seed in parent_seeds],
            "changed_expansion_seed_ids": [seed.seed_id for seed in expansion_seeds],
        }

    def _shot_one_collect_parent_entities(self, seeds: List[ParentSeed]) -> List[ParentEntity]:
        entities: List[ParentEntity] = []
        for seed in seeds:
            entities.append(
                ParentEntity(
                    name=seed.name,
                    category=seed.category,
                    notes=f"seeded parent entity; seed_id={seed.seed_id}; seed_type={seed.seed_type}",
                )
            )
        return entities

    def _shot_two_expand_to_college_level(
        self, parent_entities: List[ParentEntity]
    ) -> List[OrgRecord]:
        """
        Baseline mock expansion:
        - create predictable examples from parent entities
        - demonstrates data shape and dedupe logic
        Replace this with compliant source connectors and extraction logic.
        """
        records: List[OrgRecord] = []
        demo_schools = [("Austin", "TX"), ("Los Angeles", "CA"), ("Madison", "WI")]

        for entity in parent_entities:
            for city, state in demo_schools:
                slug = entity.name.lower().replace(" ", "")
                club_name = f"{entity.name} - {city} Chapter"
                records.append(
                    OrgRecord(
                        email=f"contact@{slug}.{state.lower()}.edu",
                        name=club_name,
                        business_name=club_name,
                        category=entity.category,
                        location=f"{city}, {state}",
                        city=city,
                        state=state,
                        followers="",
                        website="",
                        instagram=f"https://instagram.com/{slug}_{city.lower().replace(' ', '')}",
                        notes="demo generated record; replace with scraper connectors",
                    )
                )

                # Intentional near-duplicate to validate dedupe behavior.
                records.append(
                    OrgRecord(
                        email="",
                        name=club_name,
                        business_name=f"{entity.name} {city} Chapter",
                        category=entity.category,
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

    def _mark_parent_seeds_processed(
        self,
        run_id: int,
        registry_entries: List[SeedRegistryEntry],
        seeds: List[ParentSeed],
    ) -> None:
        processed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
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
