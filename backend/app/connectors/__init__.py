from __future__ import annotations

from .mock import MockExpansionConnector, MockParentDirectoryConnector
from .real import SacnasChapterDirectoryConnector, SacnasParentDirectoryConnector


def build_connector_registry() -> dict[str, object]:
    return {
        "mock_parent_directory": MockParentDirectoryConnector(),
        "sacnas_parent_directory": SacnasParentDirectoryConnector(),
        "sacnas_chapter_directory": SacnasChapterDirectoryConnector(),
        "campus_directory": MockExpansionConnector("campus_directory"),
        "parent_membership_page": MockExpansionConnector("parent_membership_page"),
        "competition_directory": MockExpansionConnector("competition_directory"),
        "club_sports_directory": MockExpansionConnector("club_sports_directory"),
        "greek_life_directory": MockExpansionConnector("greek_life_directory"),
        "social_public": MockExpansionConnector("social_public"),
    }
