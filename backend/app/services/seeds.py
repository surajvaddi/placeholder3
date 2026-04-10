from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..models_seeds import (
    ExpansionSeed,
    ExpansionSeedFile,
    ParentSeed,
    ParentSeedFile,
    SeedBundle,
    SeedFamily,
    SeedRegistryEntry,
    SeedRegistryStatus,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fingerprint_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parent_seed_fingerprint(seed: ParentSeed) -> str:
    payload = {
        "seed_id": seed.seed_id,
        "name": seed.name,
        "category": seed.category,
        "seed_type": seed.seed_type,
        "source_url": seed.source_url,
        "aliases": seed.aliases,
        "enabled": seed.enabled,
        "priority": seed.priority,
        "source_hints": seed.source_hints,
        "tags": seed.tags,
    }
    return _fingerprint_payload(payload)


def _expansion_seed_fingerprint(seed: ExpansionSeed) -> str:
    payload = {
        "seed_id": seed.seed_id,
        "connector": seed.connector,
        "source_url": seed.source_url,
        "applies_to": seed.applies_to.model_dump(),
        "enabled": seed.enabled,
        "priority": seed.priority,
        "discovery_mode": seed.discovery_mode,
        "host_patterns": seed.host_patterns,
        "source_hints": seed.source_hints,
        "limits": seed.limits.model_dump(),
    }
    return _fingerprint_payload(payload)


class SeedService:
    def __init__(self, parent_seed_file: Path, expansion_seed_file: Path):
        self.parent_seed_file = parent_seed_file
        self.expansion_seed_file = expansion_seed_file

    def load_bundle(self) -> SeedBundle:
        parent_data = yaml.safe_load(self.parent_seed_file.read_text(encoding="utf-8")) or {}
        expansion_data = (
            yaml.safe_load(self.expansion_seed_file.read_text(encoding="utf-8")) or {}
        )
        parent_file = ParentSeedFile.model_validate(parent_data)
        expansion_file = ExpansionSeedFile.model_validate(expansion_data)
        self._ensure_unique_ids(parent_file.parent_seeds, expansion_file.expansion_seeds)
        return SeedBundle(
            parent_seeds=parent_file.parent_seeds,
            expansion_seeds=expansion_file.expansion_seeds,
        )

    def build_registry_entries(self, bundle: SeedBundle) -> list[SeedRegistryEntry]:
        seen_at = _utc_now()
        entries: list[SeedRegistryEntry] = []

        for seed in bundle.parent_seeds:
            entries.append(
                SeedRegistryEntry(
                    seed_id=seed.seed_id,
                    seed_family=SeedFamily.parent,
                    fingerprint=_parent_seed_fingerprint(seed),
                    enabled=seed.enabled,
                    payload_json=json.dumps(seed.model_dump(), sort_keys=True),
                    last_seen_at=seen_at,
                    status=(
                        SeedRegistryStatus.active if seed.enabled else SeedRegistryStatus.disabled
                    ),
                )
            )

        for seed in bundle.expansion_seeds:
            entries.append(
                SeedRegistryEntry(
                    seed_id=seed.seed_id,
                    seed_family=SeedFamily.expansion,
                    fingerprint=_expansion_seed_fingerprint(seed),
                    enabled=seed.enabled,
                    payload_json=json.dumps(seed.model_dump(), sort_keys=True),
                    last_seen_at=seen_at,
                    status=(
                        SeedRegistryStatus.active if seed.enabled else SeedRegistryStatus.disabled
                    ),
                )
            )

        return entries

    def fingerprint_parent_seed(self, seed: ParentSeed) -> str:
        return _parent_seed_fingerprint(seed)

    def fingerprint_expansion_seed(self, seed: ExpansionSeed) -> str:
        return _expansion_seed_fingerprint(seed)

    def changed_parent_seeds(
        self,
        bundle: SeedBundle,
        registry_entries: dict[tuple[str, SeedFamily], SeedRegistryEntry],
        mode: str,
        requested_seed_ids: set[str] | None = None,
    ) -> list[ParentSeed]:
        requested_seed_ids = requested_seed_ids or set()
        selected: list[ParentSeed] = []

        for seed in bundle.parent_seeds:
            if not seed.enabled:
                continue
            if mode == "seed_targeted" and seed.seed_id.lower() not in requested_seed_ids:
                continue
            if mode == "full":
                selected.append(seed)
                continue

            registry = registry_entries.get((seed.seed_id, SeedFamily.parent))
            fingerprint = _parent_seed_fingerprint(seed)
            if registry is None or registry.last_processed_fingerprint != fingerprint:
                selected.append(seed)

        return sorted(selected, key=lambda seed: (-seed.priority, seed.name.lower()))

    def changed_expansion_seeds(
        self,
        bundle: SeedBundle,
        registry_entries: dict[tuple[str, SeedFamily], SeedRegistryEntry],
        mode: str,
        requested_seed_ids: set[str] | None = None,
    ) -> list[ExpansionSeed]:
        requested_seed_ids = requested_seed_ids or set()
        selected: list[ExpansionSeed] = []

        for seed in bundle.expansion_seeds:
            if not seed.enabled:
                continue
            if mode == "seed_targeted" and seed.seed_id.lower() not in requested_seed_ids:
                continue
            if mode == "full":
                selected.append(seed)
                continue

            registry = registry_entries.get((seed.seed_id, SeedFamily.expansion))
            fingerprint = _expansion_seed_fingerprint(seed)
            if registry is None or registry.last_processed_fingerprint != fingerprint:
                selected.append(seed)

        return sorted(selected, key=lambda seed: (-seed.priority, seed.seed_id.lower()))

    def _ensure_unique_ids(
        self, parent_seeds: list[ParentSeed], expansion_seeds: list[ExpansionSeed]
    ) -> None:
        seen: set[str] = set()
        for seed in [*parent_seeds, *expansion_seeds]:
            key = seed.seed_id.lower()
            if key in seen:
                raise ValueError(f"Duplicate seed_id detected: {seed.seed_id}")
            seen.add(key)
