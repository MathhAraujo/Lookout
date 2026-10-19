from lookout.dedup import is_duplicate
from lookout.normalize import dedup_key


def test_is_duplicate_matches_cross_source_variants():
    existing = [dedup_key("Acme, Inc.", "Backend Engineer")]

    assert is_duplicate(dedup_key("ACME", "Backend Engineer - Remote"), existing)
    assert is_duplicate(dedup_key("Acme LLC", "backend engineer"), existing)


def test_is_duplicate_keeps_distinct_roles_at_same_company():
    existing = [dedup_key("Acme", "Backend Engineer")]

    assert not is_duplicate(dedup_key("Acme", "Senior Backend Engineer"), existing)
    assert not is_duplicate(dedup_key("Acme", "Product Manager"), existing)
