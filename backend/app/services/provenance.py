from __future__ import annotations

from typing import List, Optional

from ..models_sources import Evidence


def format_notes_from_evidence(
    evidence: List[Evidence], extra_notes: Optional[List[str]] = None
) -> str:
    parts: List[str] = []
    if evidence:
        connectors = ",".join(sorted({item.connector for item in evidence if item.connector}))
        urls = ",".join(item.source_url for item in evidence if item.source_url)
        if connectors:
            parts.append(f"sources={connectors}")
        if urls:
            parts.append(f"urls={urls}")
    if extra_notes:
        parts.extend(note for note in extra_notes if note)
    return "; ".join(parts)
