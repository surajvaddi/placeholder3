from pathlib import Path
from typing import List

import yaml

from .dedupe import DedupeEngine
from .models import OrgRecord, ParentEntity
from .storage import Storage


class TwoShotPipeline:
    def __init__(self, storage: Storage, seed_file: Path):
        self.storage = storage
        self.seed_file = seed_file
        self.dedupe = DedupeEngine()

    def run(self, run_id: int) -> dict:
        self.storage.update_run_status(run_id, status="running")
        parent_entities = self._shot_one_collect_parent_entities()
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
        self.storage.update_run_status(
            run_id, status="completed", deduped_count=len(deduped.records)
        )

        return {
            "parent_entity_count": len(parent_entities),
            "discovered_club_count": len(discovered),
            "deduped_count": len(deduped.records),
            "dedupe_pairs_removed": len(deduped.removed_pairs),
        }

    def _shot_one_collect_parent_entities(self) -> List[ParentEntity]:
        seed = yaml.safe_load(self.seed_file.read_text(encoding="utf-8")) or {}
        entities: List[ParentEntity] = []
        for category, names in seed.items():
            for name in names:
                entities.append(
                    ParentEntity(
                        name=name,
                        category=category,
                        notes="seeded parent entity",
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
