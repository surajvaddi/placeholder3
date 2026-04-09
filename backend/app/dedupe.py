import re
import json
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
        primary, secondary = self._rank_records(existing, incoming)

        def pick(a: str, b: str) -> str:
            return a if a else b

        merged_evidence_json = self._merge_json_object_lists(
            existing.evidence_json, incoming.evidence_json
        )
        merged_source_count = self._json_list_length(merged_evidence_json)

        return OrgRecord(
            parent_key=pick(primary.parent_key, secondary.parent_key),
            expansion_seed_id=pick(primary.expansion_seed_id, secondary.expansion_seed_id),
            email=pick(primary.email, secondary.email),
            name=pick(primary.name, secondary.name),
            business_name=pick(primary.business_name, secondary.business_name),
            category=pick(primary.category, secondary.category),
            location=pick(primary.location, secondary.location),
            city=pick(primary.city, secondary.city),
            state=pick(primary.state, secondary.state),
            followers=pick(primary.followers, secondary.followers),
            website=pick(primary.website, secondary.website),
            instagram=pick(primary.instagram, secondary.instagram),
            confidence_score=max(existing.confidence_score, incoming.confidence_score),
            review_flags_json=self._merge_json_string_lists(
                existing.review_flags_json, incoming.review_flags_json
            ),
            evidence_json=merged_evidence_json,
            source_count=max(existing.source_count, incoming.source_count, merged_source_count),
            notes=" | ".join(filter(None, [existing.notes, incoming.notes])),
            status=primary.status,
        )

    def _rank_records(self, a: OrgRecord, b: OrgRecord) -> tuple[OrgRecord, OrgRecord]:
        def score(record: OrgRecord) -> tuple[float, int, int, int]:
            return (
                record.confidence_score,
                record.source_count,
                int(bool(record.email)),
                int(bool(record.website or record.instagram)),
            )

        if score(a) >= score(b):
            return a, b
        return b, a

    def _merge_json_string_lists(self, a: str, b: str) -> str:
        items = set()
        for raw in (a, b):
            try:
                for value in json.loads(raw or "[]"):
                    items.add(str(value))
            except json.JSONDecodeError:
                continue
        return json.dumps(sorted(items))

    def _merge_json_object_lists(self, a: str, b: str) -> str:
        items: dict[str, dict] = {}
        for raw in (a, b):
            try:
                for value in json.loads(raw or "[]"):
                    key = json.dumps(value, sort_keys=True)
                    items[key] = value
            except json.JSONDecodeError:
                continue
        return json.dumps(list(items.values()), sort_keys=True)

    def _json_list_length(self, raw: str) -> int:
        try:
            return len(json.loads(raw or "[]"))
        except json.JSONDecodeError:
            return 0

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
