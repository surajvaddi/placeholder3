from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourcePolicy:
    tag: str
    host_patterns: tuple[str, ...]
    allowed_connector_names: tuple[str, ...]
    robots_required: bool = True
    min_delay_seconds: float = 1.0
    max_requests_per_run: int = 25
    allow_html: bool = True
    allow_json: bool = False
    notes: str = ""


class PolicyRegistry:
    def __init__(self, policies: list[SourcePolicy] | None = None):
        self._policies = policies or []

    def resolve(self, url: str, connector_name: str, policy_tag: str) -> SourcePolicy:
        host = urlparse(url).netloc.lower()
        for policy in self._policies:
            if policy.tag != policy_tag:
                continue
            if connector_name not in policy.allowed_connector_names:
                continue
            if any(fnmatch(host, pattern.lower()) for pattern in policy.host_patterns):
                return policy
        raise PermissionError(
            f"No matching source policy for host={host}, connector={connector_name}, tag={policy_tag}."
        )


def default_policy_registry() -> PolicyRegistry:
    return PolicyRegistry(
        policies=[
            SourcePolicy(
                tag="mock",
                host_patterns=("mock.local",),
                allowed_connector_names=(
                    "mock_parent_directory",
                    "campus_directory",
                    "parent_membership_page",
                    "competition_directory",
                    "club_sports_directory",
                    "greek_life_directory",
                    "social_public",
                ),
                robots_required=False,
                min_delay_seconds=0.0,
                max_requests_per_run=1000,
                allow_html=True,
                allow_json=True,
                notes="Local mock policy used during architecture phases.",
            ),
            SourcePolicy(
                tag="sacnas_official",
                host_patterns=("www.sacnas.org", "sacnas.org"),
                allowed_connector_names=(
                    "sacnas_parent_directory",
                    "sacnas_chapter_directory",
                ),
                robots_required=True,
                min_delay_seconds=1.0,
                max_requests_per_run=20,
                allow_html=True,
                allow_json=False,
                notes="Official SACNAS chapter directory access.",
            )
        ]
    )
