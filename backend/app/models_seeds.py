from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class SeedFamily(str, Enum):
    parent = "parent"
    expansion = "expansion"


class SeedRegistryStatus(str, Enum):
    active = "active"
    disabled = "disabled"
    superseded = "superseded"
    error = "error"


class ParentSeed(BaseModel):
    seed_id: str = Field(min_length=3, max_length=100)
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=2, max_length=100)
    seed_type: str = Field(min_length=2, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 10
    source_hints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    updated_at: str = ""

    @field_validator("seed_id", "category", "seed_type")
    @classmethod
    def normalize_slug_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("aliases", "source_hints", "tags")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for value in values:
            normalized = " ".join(value.split())
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(normalized)
        return cleaned


class AppliesTo(BaseModel):
    categories: list[str] = Field(default_factory=list)
    seed_types: list[str] = Field(default_factory=list)
    seed_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("categories", "seed_types", "seed_ids", "tags")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(normalized)
        return cleaned

    @model_validator(mode="after")
    def ensure_scope_present(self) -> "AppliesTo":
        if not (self.categories or self.seed_types or self.seed_ids or self.tags):
            raise ValueError("Expansion seed applies_to must define at least one scope.")
        return self


class ExpansionSeedLimits(BaseModel):
    max_requests_per_parent: int = Field(default=10, ge=1)
    max_results_per_parent: int = Field(default=100, ge=1)


class ExpansionSeed(BaseModel):
    seed_id: str = Field(min_length=3, max_length=100)
    connector: str = Field(min_length=2, max_length=100)
    applies_to: AppliesTo
    enabled: bool = True
    priority: int = 10
    discovery_mode: str = Field(min_length=2, max_length=100)
    host_patterns: list[str] = Field(default_factory=list)
    source_hints: list[str] = Field(default_factory=list)
    limits: ExpansionSeedLimits = Field(default_factory=ExpansionSeedLimits)
    notes: str = ""
    updated_at: str = ""

    @field_validator("seed_id", "connector", "discovery_mode")
    @classmethod
    def normalize_slug_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("host_patterns", "source_hints")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(normalized)
        return cleaned

    @model_validator(mode="after")
    def ensure_host_patterns_for_host_bound_connector(self) -> "ExpansionSeed":
        if self.connector in {"campus_directory", "parent_membership_page"} and not self.host_patterns:
            raise ValueError("Host-bound expansion seeds must define host_patterns.")
        return self


class ParentSeedFile(BaseModel):
    version: int = 1
    parent_seeds: list[ParentSeed] = Field(default_factory=list)


class ExpansionSeedFile(BaseModel):
    version: int = 1
    expansion_seeds: list[ExpansionSeed] = Field(default_factory=list)


class SeedRegistryEntry(BaseModel):
    seed_id: str
    seed_family: SeedFamily
    fingerprint: str
    enabled: bool
    payload_json: str
    last_seen_at: str
    last_processed_run_id: int | None = None
    last_processed_fingerprint: str | None = None
    last_success_at: str | None = None
    status: SeedRegistryStatus = SeedRegistryStatus.active


class SeedBundle(BaseModel):
    parent_seeds: list[ParentSeed] = Field(default_factory=list)
    expansion_seeds: list[ExpansionSeed] = Field(default_factory=list)
