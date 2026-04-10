from __future__ import annotations

from typing import List, Tuple

from ..models_sources import OrgRecordCandidate, ParentEntityCandidate, ReviewFlag


def score_parent_candidate(candidate: ParentEntityCandidate) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []

    if candidate.source_url:
        score += 2
        reasons.append("has_source_url")
    if candidate.seed_type in {"national_org", "conference", "fraternity_sorority"}:
        score += 2
        reasons.append("strong_seed_type")
    if candidate.evidence:
        score += min(len(candidate.evidence), 2)
        reasons.append("has_evidence")

    return score, reasons


def score_org_candidate(candidate: OrgRecordCandidate) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []

    if candidate.email:
        score += 3
        reasons.append("has_email")
    if candidate.website:
        score += 2
        reasons.append("has_website")
    if candidate.instagram:
        score += 1
        reasons.append("has_instagram")
    if candidate.city and candidate.state:
        score += 1
        reasons.append("has_geo")
    if candidate.evidence:
        score += min(len(candidate.evidence), 2)
        reasons.append("has_evidence")
    if ReviewFlag.social_only in candidate.review_flags:
        score -= 2
        reasons.append("social_only_penalty")
    if ReviewFlag.ambiguous_name in candidate.review_flags:
        score -= 2
        reasons.append("ambiguous_name_penalty")

    return score, reasons
