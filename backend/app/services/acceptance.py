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
    has_website = bool(candidate.website)
    has_instagram = bool(candidate.instagram)
    has_web_signal = bool(has_website or has_instagram)
    has_school_signal = bool(candidate.city and candidate.state)
    normalized_name = candidate.business_name.lower().strip()

    if has_email:
        reasons.append("public_email_present")
    if has_website:
        reasons.append("website_present")
    if has_instagram:
        reasons.append("instagram_present")
    if has_school_signal:
        reasons.append("geo_signal_present")
    if has_email and has_website:
        reasons.append("outreach_primary_ready")
    elif has_email:
        reasons.append("outreach_email_ready")
    elif has_website:
        reasons.append("outreach_website_only")
    elif has_instagram:
        reasons.append("outreach_instagram_only")

    if len(normalized_name) < 4 or normalized_name in {"club", "chapter", "student organization"}:
        if ReviewFlag.ambiguous_name not in flags:
            flags.append(ReviewFlag.ambiguous_name)
        reasons.append("ambiguous_name")

    if has_instagram and not has_website and not has_email:
        if ReviewFlag.social_only not in flags:
            flags.append(ReviewFlag.social_only)
        reasons.append("social_only_signal")

    if has_email:
        return AcceptanceDecision("accepted", flags, reasons)
    if has_website and has_school_signal:
        return AcceptanceDecision("accepted", flags, reasons)
    if has_website:
        if ReviewFlag.weak_source not in flags:
            flags.append(ReviewFlag.weak_source)
        return AcceptanceDecision("accepted_with_review", flags, reasons)
    if has_instagram and has_school_signal:
        return AcceptanceDecision("accepted_with_review", flags, reasons)
    if has_instagram:
        if ReviewFlag.weak_source not in flags:
            flags.append(ReviewFlag.weak_source)
        return AcceptanceDecision("accepted_with_review", flags, reasons)
    return AcceptanceDecision("rejected", flags, reasons)
