from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RecordStatus(str, Enum):
    new = "new"
    reviewed = "reviewed"
    contacted = "contacted"
    do_not_contact = "do_not_contact"


class ParentEntity(BaseModel):
    name: str
    category: str
    notes: str = ""
    source_url: Optional[str] = None


class OrgRecord(BaseModel):
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


class RunResponse(BaseModel):
    run_id: int
    run_name: str
    status: str
    parent_entity_count: int = 0
    discovered_club_count: int = 0
    deduped_count: int = 0
    notes: str = ""
