import re


def normalize_name(value: str) -> str:
    return " ".join(value.split())


def canonical_instagram(value: str) -> str:
    if not value:
        return ""
    normalized = value.strip().lower()
    normalized = normalized.replace("https://instagram.com/", "")
    normalized = normalized.replace("https://www.instagram.com/", "")
    return normalized.strip("/").replace("@", "")


def canonical_website(value: str) -> str:
    if not value:
        return ""
    normalized = value.strip().lower()
    normalized = normalized.replace("https://", "").replace("http://", "")
    normalized = normalized.replace("www.", "")
    return normalized.rstrip("/")


def normalize_city(value: str) -> str:
    return normalize_name(value).title()


def normalize_state(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).upper()
