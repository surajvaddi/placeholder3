from __future__ import annotations

from typing import Dict

from .mock import MockExpansionConnector, MockParentDirectoryConnector
from .real import (
    GenericDirectoryExpansionConnector,
    OfficialSeedPageConnector,
    SacnasChapterDirectoryConnector,
    SacnasParentDirectoryConnector,
    SocialPublicConnector,
)


def build_connector_registry() -> Dict[str, object]:
    return {
        "official_seed_page": OfficialSeedPageConnector(),
        "mock_parent_directory": MockParentDirectoryConnector(),
        "sacnas_parent_directory": SacnasParentDirectoryConnector(),
        "sacnas_chapter_directory": SacnasChapterDirectoryConnector(),
        "campus_directory": GenericDirectoryExpansionConnector("campus_directory"),
        "parent_membership_page": GenericDirectoryExpansionConnector("parent_membership_page"),
        "competition_directory": GenericDirectoryExpansionConnector("competition_directory"),
        "club_sports_directory": GenericDirectoryExpansionConnector("club_sports_directory"),
        "greek_life_directory": GenericDirectoryExpansionConnector("greek_life_directory"),
        "social_public": SocialPublicConnector(),
    }
