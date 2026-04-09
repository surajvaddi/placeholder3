import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from rapidfuzz import fuzz

from .models import OrgRecord


def _normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _canonical_website(url: str) -> str:
    if not url:
        return ""
    v = url.lower().strip()
    v = v.replace("https://", "").replace("http://", "")
    v = v.replace("www.", "")
    return v.rstrip("/")


def _canonical_instagram(instagram: str) -> str:
    if not instagram:
        return ""
    v = instagram.lower().strip()
    v = v.replace("https://instagram.com/", "").replace("https://www.instagram.com/", "")
    return v.strip("/").replace("@", "")


def _record_signature(record: OrgRecord) -> str:
    return "|".join(
        [
            _normalize_text(record.business_name),
            _normalize_text(record.name),
            _normalize_text(record.city),
            _normalize_text(record.state),
            _canonical_website(record.website),
            _canonical_instagram(record.instagram),
        ]
    )


@dataclass
class DedupeResult:
    records: List[OrgRecord]
    removed_pairs: List[Tuple[str, str]]


class DedupeEngine:
    """
    Dedupes using layered matching:
    1) hard keys (email, website, instagram)
    2) exact signature
    3) fuzzy business-name + geo check
    """

    def __init__(self, fuzzy_threshold: int = 92):
        self.fuzzy_threshold = fuzzy_threshold

    def run(self, records: Iterable[OrgRecord]) -> DedupeResult:
        unique: List[OrgRecord] = []
        removed_pairs: List[Tuple[str, str]] = []
        email_idx: Dict[str, OrgRecord] = {}
        website_idx: Dict[str, OrgRecord] = {}
        insta_idx: Dict[str, OrgRecord] = {}
        signature_idx: Dict[str, OrgRecord] = {}

        for incoming in records:
            existing = self._find_existing(
                incoming, unique, email_idx, website_idx, insta_idx, signature_idx
            )
            if existing:
                merged = self._merge_records(existing, incoming)
                unique[unique.index(existing)] = merged
                self._refresh_indexes(merged, email_idx, website_idx, insta_idx, signature_idx)
                removed_pairs.append((incoming.business_name, existing.business_name))
                continue

            unique.append(incoming)
            self._refresh_indexes(incoming, email_idx, website_idx, insta_idx, signature_idx)

        return DedupeResult(records=unique, removed_pairs=removed_pairs)

    def _find_existing(
        self,
        incoming: OrgRecord,
        unique: List[OrgRecord],
        email_idx: Dict[str, OrgRecord],
        website_idx: Dict[str, OrgRecord],
        insta_idx: Dict[str, OrgRecord],
        signature_idx: Dict[str, OrgRecord],
    ) -> OrgRecord | None:
        if incoming.email and incoming.email.lower() in email_idx:
            return email_idx[incoming.email.lower()]

        website = _canonical_website(incoming.website)
        if website and website in website_idx:
            return website_idx[website]

        instagram = _canonical_instagram(incoming.instagram)
        if instagram and instagram in insta_idx:
            return insta_idx[instagram]

        sig = _record_signature(incoming)
        if sig in signature_idx:
            return signature_idx[sig]

        for candidate in unique:
            if self._is_fuzzy_duplicate(incoming, candidate):
                return candidate
        return None

    def _is_fuzzy_duplicate(self, a: OrgRecord, b: OrgRecord) -> bool:
        if _normalize_text(a.state) != _normalize_text(b.state):
            return False
        if a.city and b.city and _normalize_text(a.city) != _normalize_text(b.city):
            return False

        score = fuzz.token_set_ratio(
            _normalize_text(a.business_name), _normalize_text(b.business_name)
        )
        return score >= self.fuzzy_threshold

    def _merge_records(self, existing: OrgRecord, incoming: OrgRecord) -> OrgRecord:
        def pick(a: str, b: str) -> str:
            return a if a else b

        return OrgRecord(
            email=pick(existing.email, incoming.email),
            name=pick(existing.name, incoming.name),
            business_name=pick(existing.business_name, incoming.business_name),
            category=pick(existing.category, incoming.category),
            location=pick(existing.location, incoming.location),
            city=pick(existing.city, incoming.city),
            state=pick(existing.state, incoming.state),
            followers=pick(existing.followers, incoming.followers),
            website=pick(existing.website, incoming.website),
            instagram=pick(existing.instagram, incoming.instagram),
            notes=" | ".join(filter(None, [existing.notes, incoming.notes])),
            status=existing.status,
        )

    def _refresh_indexes(
        self,
        record: OrgRecord,
        email_idx: Dict[str, OrgRecord],
        website_idx: Dict[str, OrgRecord],
        insta_idx: Dict[str, OrgRecord],
        signature_idx: Dict[str, OrgRecord],
    ) -> None:
        if record.email:
            email_idx[record.email.lower()] = record
        if record.website:
            website_idx[_canonical_website(record.website)] = record
        if record.instagram:
            insta_idx[_canonical_instagram(record.instagram)] = record
        signature_idx[_record_signature(record)] = record
