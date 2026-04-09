from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import ParentEntity
from ..models_seeds import ExpansionSeed, ParentSeed
from ..models_sources import OrgRecordCandidate, ParentEntityCandidate


@dataclass
class ConnectorContext:
    run_id: int


class BaseConnector(Protocol):
    connector_name: str

    def supports_shot_one(self) -> bool: ...
    def supports_shot_two(self) -> bool: ...

    async def discover_parent_entities(
        self,
        seed: ParentSeed,
        fetcher,
        context: ConnectorContext,
    ) -> list[ParentEntityCandidate]: ...

    async def discover_org_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        fetcher,
        context: ConnectorContext,
    ) -> list[OrgRecordCandidate]: ...
