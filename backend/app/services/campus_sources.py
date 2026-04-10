from __future__ import annotations

from typing import List, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

COMMON_DIRECTORY_PATHS = (
    "/clubs",
    "/engage",
    "/organizations",
    "/presence",
    "/student-life/clubs-organizations",
    "/student-life/get-involved",
    "/student-life/organizations",
    "/student-life/student-organizations",
    "/student-activities",
    "/student-activities/student-organizations",
    "/student-affairs/student-organizations",
    "/student-involvement",
    "/student-orgs",
    "/student-organizations",
)
TRUSTED_DIRECTORY_HOST_MARKERS = (
    "campusgroups.com",
    "campuslabs.com",
    "collegiatelink.net",
    "presence.io",
)


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


def _is_same_host(left: str, right: str) -> bool:
    return urlparse(left).netloc.lower() == urlparse(right).netloc.lower()


def _is_trusted_directory_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(marker in host for marker in TRUSTED_DIRECTORY_HOST_MARKERS)


def _anchor_score(text: str, href: str, keywords: Sequence[str]) -> int:
    haystack = f"{text} {href}".lower()
    return sum(1 for keyword in keywords if keyword and keyword in haystack)


async def discover_campus_directory_pages(
    fetcher,
    start_url: str,
    policy_tag: str,
    keywords: Sequence[str],
    max_pages: int,
) -> List[Tuple[str, BeautifulSoup]]:
    response = await fetcher.get_text(start_url, policy_tag=policy_tag)
    root_url = str(response.url)
    pages: List[Tuple[str, BeautifulSoup]] = [(root_url, BeautifulSoup(response.text, "lxml"))]
    seen_urls: Set[str] = {root_url}
    candidate_urls: List[Tuple[int, str]] = []

    root_soup = pages[0][1]
    for anchor in root_soup.find_all("a", href=True):
        href = urljoin(root_url, anchor["href"])
        if not href.startswith(("http://", "https://")):
            continue
        if not (_is_same_host(root_url, href) or _is_trusted_directory_host(href)):
            continue
        if href in seen_urls:
            continue
        text = _normalize_space(anchor.get_text(" ", strip=True))
        score = _anchor_score(text, href, keywords)
        if score <= 0:
            continue
        seen_urls.add(href)
        candidate_urls.append((score + 20, href))

    parsed_root = urlparse(root_url)
    for path in COMMON_DIRECTORY_PATHS:
        candidate = f"{parsed_root.scheme}://{parsed_root.netloc}{path}"
        if candidate in seen_urls:
            continue
        seen_urls.add(candidate)
        candidate_urls.append((10, candidate))

    for _, candidate_url in sorted(candidate_urls, key=lambda item: (-item[0], item[1]))[: max_pages - 1]:
        try:
            candidate_response = await fetcher.get_text(candidate_url, policy_tag=policy_tag)
        except Exception:  # noqa: BLE001
            continue
        soup = BeautifulSoup(candidate_response.text, "lxml")
        page_text = _normalize_space(soup.get_text(" ", strip=True)).lower()
        if not any(keyword in page_text or keyword in candidate_url.lower() for keyword in keywords):
            continue
        pages.append((str(candidate_response.url), soup))

    return pages
