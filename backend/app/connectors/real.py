from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .base import ConnectorContext
from ..models import ParentEntity
from ..models_seeds import ExpansionSeed, ParentSeed
from ..models_sources import Evidence, OrgRecordCandidate, ParentEntityCandidate
from ..services.normalizer import normalize_name, normalize_state

SACNAS_DIRECTORY_URL = "https://www.sacnas.org/chapters/chapter-directory"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
    ) -> list[ParentEntityCandidate]:
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
    ) -> list[OrgRecordCandidate]:
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
    ) -> list[ParentEntityCandidate]:
        raise NotImplementedError

    async def discover_org_records(
        self,
        parent: ParentEntity,
        expansion_seed: ExpansionSeed,
        fetcher,
        context: ConnectorContext,
    ) -> list[OrgRecordCandidate]:
        page = await fetcher.get_text(SACNAS_DIRECTORY_URL, policy_tag="sacnas_official")
        soup = BeautifulSoup(page.text, "lxml")
        chapter_heading = soup.find("h2", string=lambda s: s and "Chapters by State" in s)
        if chapter_heading is None:
            return []

        current_state = ""
        records: list[OrgRecordCandidate] = []

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

    def _clean_chapter_name(self, value: str) -> tuple[str, bool, bool]:
        provisional = value.endswith("*")
        cleaned = value.rstrip("*").strip()
        professional = "(Professional Chapter)" in cleaned
        cleaned = cleaned.replace("(Professional Chapter)", "").strip()
        cleaned = cleaned.replace(" - ", " ")
        cleaned = normalize_name(cleaned)
        return cleaned, provisional, professional
