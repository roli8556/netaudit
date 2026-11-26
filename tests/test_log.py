"""Tests for netaudit/log.py."""

import json
from datetime import datetime

import pytest

from netaudit.log import LogCategory, LogEntry, LogLevel


def test_entry_defaults_to_info_and_now() -> None:
    """Level and time don't have to be given."""
    before = datetime.now()
    entry = LogEntry("Project created", LogCategory.PROJECT)
    assert entry.level == LogLevel.INFO
    assert before <= entry.time <= datetime.now()


def test_entry_survives_a_round_trip() -> None:
    """An entry turned into a line and back is the same entry."""
    entry = LogEntry("Login failed", LogCategory.HOST, LogLevel.SECURITY, datetime(2026, 1, 2, 3, 4, 5))
    assert LogEntry.from_line(entry.to_line()) == entry


def test_line_break_in_message_stays_on_one_line() -> None:
    """A message can't fake an extra entry in the log file."""
    message = 'SW1\n{"level": "INFO", "message": "fake"}'
    line = LogEntry(message, LogCategory.SCAN).to_line()
    assert "\n" not in line
    assert LogEntry.from_line(line).message == message


@pytest.mark.parametrize("key, value", [("level", "DEBUG"), ("category", "OTHER")])
def test_unknown_level_or_category_raises(key: str, value: str) -> None:
    """Only the values in the enums are accepted."""
    data = json.loads(LogEntry("x", LogCategory.MISC).to_line())
    data[key] = value
    with pytest.raises(ValueError):
        LogEntry.from_line(json.dumps(data))


def test_line_that_is_not_json_raises() -> None:
    """A damaged line is an error, not an empty entry."""
    with pytest.raises(ValueError):
        LogEntry.from_line("not json")
