from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..models_sources import OrgRecordCandidate, ReviewFlag


@dataclass
class AcceptanceDecision:
    outcome: str
    review_flags: List[ReviewFlag]
    reasons: List[str]


def evaluate_org_candidate(candidate: OrgRecordCandidate) -> AcceptanceDecision:
    flags = list(candidate.review_flags)
    reasons: List[str] = []

    has_email = bool(candidate.email)
    has_web_signal = bool(candidate.website or candidate.instagram)
    has_school_signal = bool(candidate.city and candidate.state)
    normalized_name = candidate.business_name.lower().strip()

    if has_email:
        reasons.append("public_email_present")
    if has_web_signal:
        reasons.append("web_or_social_present")
    if has_school_signal:
        reasons.append("geo_signal_present")

    if len(normalized_name) < 4 or normalized_name in {"club", "chapter", "student organization"}:
        if ReviewFlag.ambiguous_name not in flags:
            flags.append(ReviewFlag.ambiguous_name)
        reasons.append("ambiguous_name")

    if candidate.instagram and not candidate.website and not candidate.email:
        if ReviewFlag.social_only not in flags:
            flags.append(ReviewFlag.social_only)
        reasons.append("social_only_signal")

    if has_email:
        return AcceptanceDecision("accepted", flags, reasons)
    if has_web_signal and has_school_signal and ReviewFlag.social_only not in flags:
        return AcceptanceDecision("accepted", flags, reasons)
    if has_web_signal and has_school_signal:
        return AcceptanceDecision("accepted_with_review", flags, reasons)
    if has_web_signal:
        if ReviewFlag.weak_source not in flags:
            flags.append(ReviewFlag.weak_source)
        return AcceptanceDecision("accepted_with_review", flags, reasons)
    return AcceptanceDecision("rejected", flags, reasons)
