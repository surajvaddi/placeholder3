from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class ReviewFlag(str, Enum):
    ambiguous_name = "ambiguous_name"
    weak_source = "weak_source"
    conflicting_geo = "conflicting_geo"
    social_only = "social_only"


class Evidence(BaseModel):
    connector: str
    source_url: str = ""
    source_type: str
    observed_at: str
    snippet: str = ""
    confidence_note: str = ""


class ParentEntityCandidate(BaseModel):
    parent_key: str = ""
    name: str
    category: str
    seed_type: str = ""
    source_seed_id: str = ""
    source_url: str = ""
    notes: str = ""
    confidence_score: float = 0.0
    evidence: List[Evidence] = Field(default_factory=list)


class OrgRecordCandidate(BaseModel):
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
    notes: str = ""
    confidence_score: float = 0.0
    review_flags: List[ReviewFlag] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
