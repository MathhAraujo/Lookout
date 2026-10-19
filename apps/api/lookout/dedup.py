from collections.abc import Sequence

from rapidfuzz import fuzz


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
        title_matches = fuzz.token_sort_ratio(candidate_title, existing_title) >= title_threshold
        if company_matches and title_matches:
            return True

    return False
