from datetime import UTC, datetime, timedelta

import pytest
from lookout.routing import initial_status_for_lane, review_expiration_for_lane


@pytest.mark.parametrize(
    ("lane", "status"),
    [
        ("auto_apply", "ready"),
        ("review", "awaiting_review"),
        ("manual_assist", "manual_assist"),
        ("rejected", "rejected"),
    ],
)
def test_initial_status_matches_each_lane(lane, status):
    assert initial_status_for_lane(lane) == status


def test_review_expiration_is_seven_days_only_for_review_lane():
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

    assert review_expiration_for_lane("review", now) == now + timedelta(days=7)
    assert review_expiration_for_lane("auto_apply", now) is None
    assert review_expiration_for_lane("manual_assist", now) is None
    assert review_expiration_for_lane("rejected", now) is None


def test_unknown_lane_is_rejected_before_persistence():
    with pytest.raises(ValueError, match="unknown application lane"):
        initial_status_for_lane("unknown")
