from collections.abc import Sequence

from rapidfuzz import fuzz

_LEVEL_MARKERS = {
    "associate",
    "entry",
    "intern",
    "intermediate",
    "junior",
    "jr",
    "lead",
    "mid",
    "principal",
    "senior",
    "sr",
    "staff",
    "i",
    "ii",
    "iii",
    "iv",
    "v",
}
_LEVEL_ALIASES = {
    "jr": "junior",
    "sr": "senior",
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
}


def _title_level_markers(title: str) -> set[str]:
    tokens = title.casefold().split()
    return {
        _LEVEL_ALIASES.get(token, token)
        for token in tokens
        if token in _LEVEL_MARKERS or token.isdigit()
    }


def is_duplicate(
    candidate_key: str,
    existing_keys: Sequence[str],
    *,
    company_threshold: float = 90.0,
    title_threshold: float = 90.0,
) -> bool:
    candidate_company, separator, candidate_title = candidate_key.partition("|")
    if not separator or not candidate_company or not candidate_title:
        return False

    for existing_key in existing_keys:
        existing_company, separator, existing_title = existing_key.partition("|")
        if not separator or not existing_company or not existing_title:
            continue

        company_matches = (
            fuzz.token_set_ratio(candidate_company, existing_company) >= company_threshold
        )
        if _title_level_markers(candidate_title) != _title_level_markers(existing_title):
            continue

        title_matches = fuzz.token_sort_ratio(candidate_title, existing_title) >= title_threshold
        if company_matches and title_matches:
            return True

    return False
