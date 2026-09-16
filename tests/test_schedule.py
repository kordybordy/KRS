from datetime import datetime, timedelta

import pytest

from krs_monitor.schedule import is_report_due, next_report_at


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        ("2026-09-17T09:00:00+02:00", False),
        ("2026-09-24T09:00:00+02:00", False),
        ("2026-10-01T06:59:00+00:00", False),
        ("2026-10-01T07:00:00+00:00", True),
        ("2026-10-01T12:00:00+02:00", True),  # A delayed GitHub run remains eligible.
        ("2026-10-02T09:00:00+02:00", False),
        ("2026-10-08T09:00:00+02:00", False),
        ("2026-10-15T09:00:00+02:00", True),
        ("2026-10-22T09:00:00+02:00", False),
        ("2026-10-29T07:59:00+00:00", False),
        ("2026-10-29T08:00:00+00:00", True),  # Winter time, still 09:00 Warsaw.
        ("2027-01-07T09:00:00+01:00", True),  # No ISO week parity reset at New Year.
        ("2027-01-14T09:00:00+01:00", False),
    ],
)
def test_fortnightly_schedule(at: str, expected: bool) -> None:
    assert is_report_due(datetime.fromisoformat(at)) is expected


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        ("2026-09-16T13:00:00+02:00", "2026-10-01T09:00:00+02:00"),
        ("2026-09-17T09:00:00+02:00", "2026-10-01T09:00:00+02:00"),
        ("2026-09-24T09:00:00+02:00", "2026-10-01T09:00:00+02:00"),
        ("2026-10-01T08:59:00+02:00", "2026-10-01T09:00:00+02:00"),
        ("2026-10-01T09:00:00+02:00", "2026-10-15T09:00:00+02:00"),
        ("2026-10-15T09:00:00+02:00", "2026-10-29T09:00:00+01:00"),
        ("2027-03-25T09:00:00+01:00", "2027-04-01T09:00:00+02:00"),
    ],
)
def test_next_report_preserves_warsaw_wall_clock(at: str, expected: str) -> None:
    assert next_report_at(datetime.fromisoformat(at)).isoformat() == expected


def test_each_report_date_is_fourteen_calendar_days_after_the_previous() -> None:
    current = datetime.fromisoformat("2026-09-16T12:00:00+02:00")
    previous = None
    for _ in range(40):
        current = next_report_at(current)
        assert current.weekday() == 3
        assert (current.hour, current.minute) == (9, 0)
        assert is_report_due(current)
        assert not is_report_due(current + timedelta(days=7))
        if previous:
            assert (current.date() - previous.date()).days == 14
        previous = current


def test_schedule_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        is_report_due(datetime(2026, 10, 1, 9))
