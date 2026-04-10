from __future__ import annotations

from enum import Enum
from typing import List, Optional, Set

from pydantic import BaseModel, Field, model_validator


class RecordStatus(str, Enum):
    new = "new"
    reviewed = "reviewed"
    contacted = "contacted"
    do_not_contact = "do_not_contact"


class RunMode(str, Enum):
    full = "full"
    incremental = "incremental"
    seed_targeted = "seed_targeted"


class ParentEntity(BaseModel):
    parent_key: str = ""
    name: str
    category: str
    seed_type: str = ""
    source_seed_id: str = ""
    confidence_score: float = 0.0
    evidence_json: str = "[]"
    notes: str = ""
    source_url: Optional[str] = None


class OrgRecord(BaseModel):
    parent_key: str = ""
    expansion_seed_id: str = ""
    email: str = ""
    name: str
    business_name: str
    category: str
    location: str = ""
    city: str = ""
    state: str = ""
    followers: str = ""
    website: str = ""
    instagram: str = ""
    confidence_score: float = 0.0
    review_flags_json: str = "[]"
    evidence_json: str = "[]"
    source_count: int = 0
    notes: str = ""
    status: RecordStatus = RecordStatus.new

    def to_csv_row(self) -> dict:
        return {
            "email": self.email,
            "name": self.name,
            "business_name": self.business_name,
            "category": self.category,
            "location": self.location,
            "city": self.city,
            "state": self.state,
            "followers": self.followers,
            "website": self.website,
            "instagram": self.instagram,
            "notes": self.notes,
            "status": self.status.value,
        }


class RunCreateRequest(BaseModel):
    run_name: str = Field(min_length=2, max_length=100)
    notes: str = ""
    mode: RunMode = RunMode.incremental
    seed_ids: List[str] = Field(default_factory=list)

    @property
    def normalized_seed_ids(self) -> List[str]:
        seen: Set[str] = set()
        values: List[str] = []
        for seed_id in self.seed_ids:
            normalized = seed_id.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            values.append(normalized)
        return values

    @model_validator(mode="after")
    def validate_mode(self) -> "RunCreateRequest":
        if self.mode == RunMode.seed_targeted and not self.normalized_seed_ids:
            raise ValueError("seed_ids are required when mode is seed_targeted.")
        return self


class RunResponse(BaseModel):
    run_id: int
    run_name: str
    status: str
    run_mode: RunMode = RunMode.incremental
    parent_entity_count: int = 0
    discovered_club_count: int = 0
    deduped_count: int = 0
    notes: str = ""
