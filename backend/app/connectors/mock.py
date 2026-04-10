from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from .base import ConnectorContext
from ..models import ParentEntity
from ..models_seeds import ExpansionSeed, ParentSeed
from ..models_sources import Evidence, OrgRecordCandidate, ParentEntityCandidate
from ..services.normalizer import normalize_city, normalize_name, normalize_state


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MockParentDirectoryConnector:
    connector_name = "mock_parent_directory"

    def supports_shot_one(self) -> bool:
        return True

    def supports_shot_two(self) -> bool:
        return False

    async def discover_parent_entities(
        self,
        seed: ParentSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[ParentEntityCandidate]:
        return [
            ParentEntityCandidate(
                name=seed.name,
                category=seed.category,
                seed_type=seed.seed_type,
                source_seed_id=seed.seed_id,
                source_url=f"https://mock.local/parents/{seed.seed_id}",
                notes=f"mock parent candidate for seed_id={seed.seed_id}",
                evidence=[
                    Evidence(
                        connector=self.connector_name,
                        source_url=f"https://mock.local/parents/{seed.seed_id}",
                        source_type="mock_seed",
                        observed_at=_utc_now(),
                        snippet=seed.name,
                    )
                ],
            )
        ]

    async def discover_org_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[OrgRecordCandidate]:
        raise NotImplementedError


class MockExpansionConnector:
    def __init__(self, connector_name: str):
        self.connector_name = connector_name

    def supports_shot_one(self) -> bool:
        return False

    def supports_shot_two(self) -> bool:
        return True

    async def discover_parent_entities(
        self,
        seed: ParentSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[ParentEntityCandidate]:
        raise NotImplementedError

    async def discover_org_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[OrgRecordCandidate]:
        records: List[OrgRecordCandidate] = []
        demo_schools = [("Austin", "TX"), ("Los Angeles", "CA"), ("Madison", "WI")]
        slug = parent.name.lower().replace(" ", "")
        for city, state in demo_schools:
            normalized_city = normalize_city(city)
            normalized_state = normalize_state(state)
            club_name = normalize_name(f"{parent.name} - {normalized_city} Chapter")
            evidence = [
                Evidence(
                    connector=self.connector_name,
                    source_url=f"https://mock.local/expand/{expansion_seed.seed_id}/{slug}",
                    source_type="mock_expansion",
                    observed_at=_utc_now(),
                    snippet=club_name,
                )
            ]
            records.append(
                OrgRecordCandidate(
                    parent_key=parent.parent_key,
                    expansion_seed_id=expansion_seed.seed_id,
                    email=f"contact@{slug}.{normalized_state.lower()}.edu",
                    name=club_name,
                    business_name=club_name,
                    category=parent.category,
                    location=f"{normalized_city}, {normalized_state}",
                    city=normalized_city,
                    state=normalized_state,
                    instagram=f"https://instagram.com/{slug}_{normalized_city.lower().replace(' ', '')}",
                    notes=(
                        "demo generated record; "
                        f"expansion_seed_id={expansion_seed.seed_id}; "
                        f"connector={self.connector_name}"
                    ),
                    evidence=evidence,
                )
            )
            records.append(
                OrgRecordCandidate(
                    parent_key=parent.parent_key,
                    expansion_seed_id=expansion_seed.seed_id,
                    name=club_name,
                    business_name=normalize_name(f"{parent.name} {normalized_city} Chapter"),
                    category=parent.category,
                    location=f"{normalized_city}, {normalized_state}",
                    city=normalized_city,
                    state=normalized_state,
                    instagram=f"@{slug}_{normalized_city.lower().replace(' ', '')}",
                    notes="possible duplicate variant",
                    evidence=evidence,
                )
            )
        return records
