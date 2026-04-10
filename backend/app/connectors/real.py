from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import ConnectorContext
from ..models import ParentEntity
from ..models_seeds import ExpansionSeed, ParentSeed
from ..models_sources import Evidence, OrgRecordCandidate, ParentEntityCandidate
from ..services.campus_sources import discover_campus_directory_pages
from ..services.normalizer import normalize_name, normalize_state

SACNAS_DIRECTORY_URL = "https://www.sacnas.org/chapters/chapter-directory"
MAX_DISCOVERY_PAGES = 5
MAX_RECORDS_PER_PAGE_SET = 150
GENERIC_POLICY_TAG = "generic_official"

SCHOOL_HINTS = (
    "academy",
    "college",
    "institute",
    "polytechnic",
    "school",
    "state",
    "tech",
    "university",
)
NON_SCHOOL_ALLOWLIST = {
    "cal",
    "clemson",
    "duke",
    "louisville",
    "miami",
    "northwestern",
    "notre dame",
    "pitt",
    "rutgers",
    "smu",
    "stanford",
    "syracuse",
    "ucla",
    "usc",
}
SOCIAL_HOST_MARKERS = ("instagram.com", "www.instagram.com")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
NOISE_TOKENS = {
    "about",
    "account",
    "admissions",
    "all schools",
    "apply",
    "athletes",
    "contact",
    "donate",
    "events",
    "faq",
    "find chapter",
    "find chapters",
    "home",
    "join",
    "learn more",
    "login",
    "media",
    "membership",
    "more",
    "news",
    "partners",
    "privacy policy",
    "register",
    "shop",
    "sign up",
    "sponsors",
    "staff",
    "student",
    "students",
    "visit section website",
}
GENERIC_ORG_WORDS = {
    "alliance",
    "association",
    "chapter",
    "chapters",
    "club",
    "clubs",
    "council",
    "organization",
    "organizations",
    "society",
    "student",
    "students",
    "team",
    "teams",
    "union",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _same_host(left: str, right: str) -> bool:
    return urlparse(left).netloc.lower() == urlparse(right).netloc.lower()


def _extract_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return _normalize_space(soup.title.string)
    heading = soup.find(["h1", "h2"])
    if heading:
        return _normalize_space(heading.get_text(" ", strip=True))
    return ""


def _base_keywords(values: Sequence[str]) -> List[str]:
    keywords: List[str] = []
    seen: Set[str] = set()
    for value in values:
        normalized = value.lower().strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(normalized)
    return keywords


def _seed_page_keywords(seed: ParentSeed) -> List[str]:
    keywords = _base_keywords(
        [
            "alliance",
            "association",
            "chapter",
            "chapters",
            "club",
            "clubs",
            "council",
            "directory",
            "find",
            "locator",
            "member",
            "members",
            "membership",
            "organization",
            "organizations",
            "school",
            "schools",
            "section",
            "sections",
            "society",
            "affiliate",
            "affiliates",
            "collegiate",
            "union",
            seed.name,
            *seed.aliases,
            *seed.source_hints,
            *seed.tags,
        ]
    )
    if seed.seed_type == "conference":
        keywords.extend(["institution", "institutions", "teams", "all schools"])
    return _base_keywords(keywords)


def _expansion_keywords(parent: ParentEntity, expansion_seed: ExpansionSeed) -> List[str]:
    keywords = _base_keywords(
        [
            "alliance",
            "association",
            "chapter",
            "chapters",
            "club",
            "clubs",
            "council",
            "directory",
            "find",
            "locator",
            "school",
            "schools",
            "section",
            "sections",
            "affiliate",
            "affiliates",
            "member",
            "members",
            "institution",
            "institutions",
            "organization",
            "organizations",
            "society",
            "team",
            "teams",
            "college",
            "collegiate",
            "union",
            parent.name,
            expansion_seed.connector,
            expansion_seed.discovery_mode,
            *expansion_seed.source_hints,
        ]
    )
    if parent.seed_type == "conference":
        keywords.extend(["all schools", "official school websites"])
    return _base_keywords(keywords)


def _seed_identity_terms(context: ConnectorContext, parent: ParentEntity) -> List[str]:
    raw_values = [parent.name, context.seed_name, *context.seed_aliases]
    return _base_keywords([value for value in raw_values if value])


def _variant_terms(context: ConnectorContext, parent: ParentEntity) -> List[str]:
    variants: List[str] = []
    for value in _seed_identity_terms(context, parent):
        variants.append(value)
        normalized = value.lower()
        replacements = (
            (" union", " association"),
            (" union", " alliance"),
            (" union", " organization"),
            (" association", " union"),
            (" association", " alliance"),
            (" association", " organization"),
            (" alliance", " union"),
            (" alliance", " association"),
            (" alliance", " organization"),
            (" organization", " union"),
            (" organization", " association"),
            (" organization", " alliance"),
            (" chapter", " club"),
            (" chapter", " team"),
            (" club", " chapter"),
            (" team", " chapter"),
        )
        for old, new in replacements:
            if old in normalized:
                variants.append(normalized.replace(old, new))
    return _base_keywords(variants)


def _identity_tokens(context: ConnectorContext, parent: ParentEntity) -> Set[str]:
    tokens: Set[str] = set()
    for value in _variant_terms(context, parent):
        for token in re.findall(r"[a-z0-9]+", value.lower()):
            if len(token) < 3:
                continue
            if token in GENERIC_ORG_WORDS:
                continue
            tokens.add(token)
    return tokens


def _has_identity_overlap(text: str, context: ConnectorContext, parent: ParentEntity) -> bool:
    lower = text.lower()
    if any(term in lower for term in _variant_terms(context, parent)):
        return True
    candidate_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", lower)
        if len(token) >= 3 and token not in GENERIC_ORG_WORDS
    }
    return bool(candidate_tokens.intersection(_identity_tokens(context, parent)))


async def _discover_pages(fetcher, url: str, policy_tag: str, keywords: Sequence[str]) -> List[Tuple[str, BeautifulSoup]]:
    response = await fetcher.get_text(url, policy_tag=policy_tag)
    pages: List[Tuple[str, BeautifulSoup]] = []
    root_url = str(response.url)
    root_soup = BeautifulSoup(response.text, "lxml")
    pages.append((root_url, root_soup))

    link_scores: List[Tuple[int, str]] = []
    seen_links = {root_url}
    for anchor in root_soup.find_all("a", href=True):
        href = urljoin(root_url, anchor["href"])
        if not href.startswith(("http://", "https://")):
            continue
        if not _same_host(root_url, href):
            continue
        if href in seen_links:
            continue
        text = _normalize_space(anchor.get_text(" ", strip=True))
        haystack = f"{text} {href}".lower()
        score = sum(1 for keyword in keywords if keyword and keyword in haystack)
        if score <= 0:
            continue
        seen_links.add(href)
        link_scores.append((score, href))

    for _, candidate_url in sorted(link_scores, key=lambda item: (-item[0], item[1]))[: MAX_DISCOVERY_PAGES - 1]:
        try:
            candidate_response = await fetcher.get_text(candidate_url, policy_tag=policy_tag)
        except Exception:  # noqa: BLE001
            continue
        pages.append((str(candidate_response.url), BeautifulSoup(candidate_response.text, "lxml")))

    return pages


def _text_blocks(soup: BeautifulSoup) -> List[str]:
    blocks: List[str] = []
    for tag in soup.find_all(["a", "li", "option", "p", "td", "h1", "h2", "h3", "h4", "span"]):
        text = _normalize_space(tag.get_text(" ", strip=True))
        if text:
            blocks.append(text)
    return blocks


def _clean_candidate_text(value: str) -> str:
    text = _normalize_space(value)
    text = re.sub(r"\s+\|\s+.*$", "", text)
    text = re.sub(r"\s+-\s+official.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+@[a-z0-9._]{2,}\b", "", text, flags=re.IGNORECASE)
    return text.strip(" -:")


def _clean_url(url: str) -> str:
    return url.strip()


def _is_instagram_url(url: str) -> bool:
    lower = url.lower()
    return any(marker in lower for marker in SOCIAL_HOST_MARKERS)


def _is_mailto_url(url: str) -> bool:
    return url.lower().startswith("mailto:")


def _best_container(element):
    container = element
    for tag_name in ("li", "tr", "article", "section", "div", "p"):
        candidate = element.find_parent(tag_name)
        if candidate is None:
            continue
        text = _normalize_space(candidate.get_text(" ", strip=True))
        if text and len(text) <= 600:
            container = candidate
            break
    return container


def _extract_email(text: str, container) -> str:
    for anchor in container.find_all("a", href=True):
        href = anchor["href"].strip()
        if _is_mailto_url(href):
            return href.split(":", 1)[1].strip()
    match = EMAIL_RE.search(text)
    return match.group(0) if match else ""


def _extract_instagram(container) -> str:
    for anchor in container.find_all("a", href=True):
        href = _clean_url(anchor["href"])
        if _is_instagram_url(href):
            return href
    text = _normalize_space(container.get_text(" ", strip=True))
    match = re.search(r"@([a-z0-9._]{2,})", text, flags=re.IGNORECASE)
    if match:
        return f"https://instagram.com/{match.group(1)}"
    return ""


def _extract_website(container, page_url: str) -> str:
    for anchor in container.find_all("a", href=True):
        href = _clean_url(urljoin(page_url, anchor["href"]))
        if not href.startswith(("http://", "https://")):
            continue
        if _is_instagram_url(href):
            continue
        if _same_host(page_url, href) and any(token in href.lower() for token in ("/organizations", "/student-", "/clubs", "/engage", "/presence")):
            continue
        return href
    return ""


def _looks_like_school_name(value: str) -> bool:
    text = _clean_candidate_text(value)
    lower = text.lower()
    if lower in NOISE_TOKENS:
        return False
    if len(text) < 3 or len(text) > 90:
        return False
    if ":" in text or "," in text:
        return False
    if sum(ch.isalpha() for ch in text) < 3:
        return False
    if any(token in lower for token in SCHOOL_HINTS):
        return True
    return lower in NON_SCHOOL_ALLOWLIST


def _is_noise(value: str) -> bool:
    text = _clean_candidate_text(value).lower()
    if not text:
        return True
    if text in NOISE_TOKENS:
        return True
    if text.startswith("@"):
        return True
    if text.startswith(("find ", "view ", "learn ", "explore ")):
        return True
    if len(text) < 3 or len(text) > 120:
        return True
    return False


def _dedupe_strings(values: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _dedupe_pairs(values: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen: Set[str] = set()
    result: List[Tuple[str, str]] = []
    for value, source_url in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append((value, source_url))
    return result


def _split_candidate_names(value: str) -> List[str]:
    raw = re.split(r"\s{2,}|;|•|\||\n", value)
    values: List[str] = []
    for item in raw:
        cleaned = _clean_candidate_text(item)
        if cleaned:
            values.append(cleaned)
    return values


def _extract_membership_sentence_names(text: str) -> List[str]:
    matches = re.findall(
        r"(?:membership includes|member institutions include|official school websites)(.*?)(?:\.|$)",
        text,
        flags=re.IGNORECASE,
    )
    values: List[str] = []
    for match in matches:
        normalized = match.replace(" and ", ", ")
        for item in normalized.split(","):
            cleaned = _clean_candidate_text(item)
            if _looks_like_school_name(cleaned):
                values.append(cleaned)
    return values


def _extract_school_names(pages: Sequence[Tuple[str, BeautifulSoup]]) -> List[Tuple[str, str]]:
    results: List[Tuple[str, str]] = []
    for page_url, soup in pages:
        page_text = _normalize_space(soup.get_text(" ", strip=True))
        for school_name in _extract_membership_sentence_names(page_text):
            results.append((school_name, page_url))

        for block in _text_blocks(soup):
            for candidate in _split_candidate_names(block):
                if _looks_like_school_name(candidate):
                    results.append((candidate, page_url))
    return _dedupe_pairs(results)[:MAX_RECORDS_PER_PAGE_SET]


def _short_parent_label(parent_name: str) -> str:
    words = [word for word in re.split(r"\s+", parent_name) if word]
    if len(words) <= 4:
        return parent_name
    acronym = "".join(word[0] for word in words if word[0].isalnum()).upper()
    return acronym or parent_name


def _extract_chapter_name(parent: ParentEntity, candidate: str, context: ConnectorContext) -> str:
    text = _clean_candidate_text(candidate)
    lower = text.lower()
    if _is_noise(text):
        return ""
    if _has_identity_overlap(text, context, parent) and any(
        token in lower
        for token in (
            "alliance",
            "association",
            "chapter",
            "chapters",
            "club",
            "clubs",
            "council",
            "organization",
            "organizations",
            "section",
            "sections",
            "society",
            "union",
            "affiliate",
            "affiliates",
        )
    ):
        return normalize_name(text)
    if _looks_like_school_name(text):
        return normalize_name(f"{text} {_short_parent_label(parent.name)} Chapter")
    return ""


def _extract_record_signals(
    parent: ParentEntity,
    candidate: str,
    element,
    page_url: str,
    context: ConnectorContext,
) -> Optional[dict]:
    chapter_name = _extract_chapter_name(parent, candidate, context)
    if not chapter_name:
        return None
    container = _best_container(element)
    container_text = _normalize_space(container.get_text(" ", strip=True))
    return {
        "business_name": chapter_name,
        "email": _extract_email(container_text, container),
        "instagram": _extract_instagram(container),
        "website": _extract_website(container, page_url),
    }


def _extract_chapter_names(
    parent: ParentEntity,
    pages: Sequence[Tuple[str, BeautifulSoup]],
    context: ConnectorContext,
) -> List[Tuple[str, str, str, str, str]]:
    results: List[Tuple[str, str, str, str, str]] = []
    for page_url, soup in pages:
        for element in soup.find_all(["a", "li", "option", "p", "td", "h1", "h2", "h3", "h4", "span"]):
            if element.name != "a":
                child_anchor_texts = [
                    _normalize_space(anchor.get_text(" ", strip=True))
                    for anchor in element.find_all("a", href=True)
                ]
                if any(
                    _extract_chapter_name(parent, anchor_text, context)
                    for anchor_text in child_anchor_texts
                ):
                    continue
            text = _normalize_space(element.get_text(" ", strip=True))
            if not text:
                continue
            for candidate in _split_candidate_names(text):
                signals = _extract_record_signals(parent, candidate, element, page_url, context)
                if signals:
                    results.append(
                        (
                            signals["business_name"],
                            page_url,
                            signals["email"],
                            signals["instagram"],
                            signals["website"],
                        )
                    )
    deduped: List[Tuple[str, str, str, str, str]] = []
    seen: Set[str] = set()
    for business_name, source_url, email, instagram, website in results:
        key = business_name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((business_name, source_url, email, instagram, website))
    return deduped[:MAX_RECORDS_PER_PAGE_SET]


class OfficialSeedPageConnector:
    connector_name = "official_seed_page"

    def supports_shot_one(self) -> bool:
        return True

    def supports_shot_two(self) -> bool:
        return False

    async def discover_parent_entities(
        self,
        seed: ParentSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[ParentEntityCandidate]:
        if not seed.source_url:
            return []

        pages = await _discover_pages(
            fetcher=fetcher,
            url=seed.source_url,
            policy_tag=GENERIC_POLICY_TAG,
            keywords=_seed_page_keywords(seed),
        )
        if not pages:
            return []

        best_url, best_soup = pages[0]
        best_title = _extract_title(best_soup)
        evidence_parts = [part for part in [best_title, seed.name] if part]
        evidence_snippet = " | ".join(evidence_parts)

        return [
            ParentEntityCandidate(
                name=seed.name,
                category=seed.category,
                seed_type=seed.seed_type,
                source_seed_id=seed.seed_id,
                source_url=best_url,
                notes=f"validated against official source page for seed_id={seed.seed_id}",
                evidence=[
                    Evidence(
                        connector=self.connector_name,
                        source_url=best_url,
                        source_type="official_source_page",
                        observed_at=_utc_now(),
                        snippet=evidence_snippet,
                    )
                ],
            )
        ]

    async def discover_org_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[OrgRecordCandidate]:
        raise NotImplementedError


class SacnasParentDirectoryConnector:
    connector_name = "sacnas_parent_directory"

    def supports_shot_one(self) -> bool:
        return True

    def supports_shot_two(self) -> bool:
        return False

    async def discover_parent_entities(
        self,
        seed: ParentSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[ParentEntityCandidate]:
        page = await fetcher.get_text(SACNAS_DIRECTORY_URL, policy_tag="sacnas_official")
        if "Chapter Directory" not in page.text or "SACNAS" not in page.text:
            return []

        return [
            ParentEntityCandidate(
                name=seed.name,
                category=seed.category,
                seed_type=seed.seed_type,
                source_seed_id=seed.seed_id,
                source_url=SACNAS_DIRECTORY_URL,
                notes="validated against official SACNAS chapter directory",
                confidence_score=0.0,
                evidence=[
                    Evidence(
                        connector=self.connector_name,
                        source_url=SACNAS_DIRECTORY_URL,
                        source_type="official_directory",
                        observed_at=_utc_now(),
                        snippet="SACNAS has official student and professional chapters.",
                    )
                ],
            )
        ]

    async def discover_org_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[OrgRecordCandidate]:
        raise NotImplementedError


class SacnasChapterDirectoryConnector:
    connector_name = "sacnas_chapter_directory"

    def supports_shot_one(self) -> bool:
        return False

    def supports_shot_two(self) -> bool:
        return True

    async def discover_parent_entities(
        self,
        seed: ParentSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[ParentEntityCandidate]:
        raise NotImplementedError

    async def discover_org_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[OrgRecordCandidate]:
        page = await fetcher.get_text(SACNAS_DIRECTORY_URL, policy_tag="sacnas_official")
        soup = BeautifulSoup(page.text, "lxml")
        chapter_heading = soup.find("h2", string=lambda s: s and "Chapters by State" in s)
        if chapter_heading is None:
            return []

        current_state = ""
        records: List[OrgRecordCandidate] = []

        for element in chapter_heading.find_all_next(["h2", "h3", "p"]):
            text = normalize_name(element.get_text(" ", strip=True))
            if not text:
                continue
            if element.name == "h2" and text == "Chapter Directory FAQ":
                break
            if text == "* denotes provisional chapter":
                continue
            if element.name == "h3":
                current_state = normalize_state(text)
                continue
            if element.name != "p" or not current_state:
                continue

            cleaned_name, provisional, professional = self._clean_chapter_name(text)
            if not cleaned_name:
                continue
            if professional:
                continue

            records.append(
                OrgRecordCandidate(
                    parent_key=parent.parent_key,
                    expansion_seed_id=expansion_seed.seed_id,
                    name=f"{cleaned_name} SACNAS Chapter",
                    business_name=f"{cleaned_name} SACNAS Chapter",
                    category=parent.category,
                    location=current_state,
                    city="",
                    state=current_state,
                    website=SACNAS_DIRECTORY_URL,
                    notes=(
                        "official SACNAS chapter directory listing"
                        + ("; provisional chapter" if provisional else "")
                    ),
                    evidence=[
                        Evidence(
                            connector=self.connector_name,
                            source_url=SACNAS_DIRECTORY_URL,
                            source_type="official_directory",
                            observed_at=_utc_now(),
                            snippet=cleaned_name,
                        )
                    ],
                )
            )

        return records

    def _clean_chapter_name(self, value: str) -> Tuple[str, bool, bool]:
        provisional = value.endswith("*")
        cleaned = value.rstrip("*").strip()
        professional = "(Professional Chapter)" in cleaned
        cleaned = cleaned.replace("(Professional Chapter)", "").strip()
        cleaned = cleaned.replace(" - ", " ")
        cleaned = normalize_name(cleaned)
        return cleaned, provisional, professional


class GenericDirectoryExpansionConnector:
    def __init__(self, connector_name: str):
        self.connector_name = connector_name

    def supports_shot_one(self) -> bool:
        return False

    def supports_shot_two(self) -> bool:
        return True

    async def discover_parent_entities(
        self,
        seed: ParentSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[ParentEntityCandidate]:
        raise NotImplementedError

    async def discover_org_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        fetcher,
        context: ConnectorContext,
    ) -> List[OrgRecordCandidate]:
        start_url = expansion_seed.source_url or parent.source_url or ""
        if not start_url:
            return []

        discovery_keywords = _base_keywords(
            _expansion_keywords(parent, expansion_seed) + _variant_terms(context, parent)
        )
        if self.connector_name == "campus_directory":
            pages = await discover_campus_directory_pages(
                fetcher=fetcher,
                start_url=start_url,
                policy_tag=GENERIC_POLICY_TAG,
                keywords=discovery_keywords,
                max_pages=MAX_DISCOVERY_PAGES,
            )
        else:
            pages = await _discover_pages(
                fetcher=fetcher,
                url=start_url,
                policy_tag=GENERIC_POLICY_TAG,
                keywords=discovery_keywords,
            )
        if parent.seed_type == "conference" or self.connector_name == "parent_membership_page":
            return self._school_records(parent, expansion_seed, pages)
        return self._chapter_records(parent, expansion_seed, pages, context)

    def _school_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        pages: Sequence[Tuple[str, BeautifulSoup]],
    ) -> List[OrgRecordCandidate]:
        records: List[OrgRecordCandidate] = []
        for school_name, source_url in _extract_school_names(pages):
            records.append(
                OrgRecordCandidate(
                    parent_key=parent.parent_key,
                    expansion_seed_id=expansion_seed.seed_id,
                    name=school_name,
                    business_name=school_name,
                    category=parent.category,
                    website=source_url,
                    notes=f"discovered from official member list for {parent.name}",
                    evidence=[
                        Evidence(
                            connector=self.connector_name,
                            source_url=source_url,
                            source_type="official_members_page",
                            observed_at=_utc_now(),
                            snippet=school_name,
                        )
                    ],
                )
            )
        return records

    def _chapter_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        pages: Sequence[Tuple[str, BeautifulSoup]],
        context: ConnectorContext,
    ) -> List[OrgRecordCandidate]:
        records: List[OrgRecordCandidate] = []
        for chapter_name, source_url, email, instagram, website in _extract_chapter_names(
            parent, pages, context
        ):
            records.append(
                OrgRecordCandidate(
                    parent_key=parent.parent_key,
                    expansion_seed_id=expansion_seed.seed_id,
                    name=chapter_name,
                    business_name=chapter_name,
                    category=parent.category,
                    email=email,
                    website=website or source_url,
                    instagram=instagram,
                    notes=f"discovered from official directory for {parent.name}",
                    evidence=[
                        Evidence(
                            connector=self.connector_name,
                            source_url=source_url,
                            source_type="official_directory",
                            observed_at=_utc_now(),
                            snippet=chapter_name,
                        )
                    ],
                )
            )
        return records


class SocialPublicConnector(GenericDirectoryExpansionConnector):
    def __init__(self):
        super().__init__("social_public")
