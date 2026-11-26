"""Tests for netaudit/log.py."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from netaudit.log import LogCategory, LogEntry, LogLevel, ProjectLog


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


@pytest.fixture
def log(tmp_path: Path) -> ProjectLog:
    """An empty log in a temporary folder, with no file yet."""
    return ProjectLog(tmp_path / "project.log")


def test_written_entries_load_back_in_order(log: ProjectLog) -> None:
    """A fresh log loaded from the file has the same entries as the one that wrote them."""
    log.write(LogEntry("Project created", LogCategory.PROJECT))
    log.write(LogEntry("Login failed", LogCategory.HOST, LogLevel.SECURITY))
    fresh = ProjectLog(log.path)
    fresh.load()
    assert fresh.entries == log.entries
    assert len(fresh.entries) == 2


def test_load_missing_file_gives_no_entries(log: ProjectLog) -> None:
    """A project without a log file yet is not an error."""
    log.load()
    assert log.entries == []


def test_load_twice_does_not_duplicate(log: ProjectLog) -> None:
    """Loading replaces the entries."""
    log.write(LogEntry("Project created", LogCategory.PROJECT))
    log.load()
    log.load()
    assert len(log.entries) == 1


def test_write_to_missing_folder_raises_and_keeps_entries(tmp_path: Path) -> None:
    """If the file can't be written, the entries in memory don't change."""
    log = ProjectLog(tmp_path / "missing" / "project.log")
    with pytest.raises(FileNotFoundError):
        log.write(LogEntry("Project created", LogCategory.PROJECT))
    assert log.entries == []


def test_blank_lines_are_ignored(log: ProjectLog) -> None:
    """Empty lines are not entries and not damage."""
    log.write(LogEntry("Project created", LogCategory.PROJECT))
    with log.path.open("a", encoding="utf-8") as file:
        file.write("\n   \n")
    log.load()
    assert len(log.entries) == 1


def test_half_written_line_is_skipped_and_kept_separate(log: ProjectLog) -> None:
    """After a crash mid-write, only the damaged line is lost, and it is reported once."""
    log.write(LogEntry("Scan started", LogCategory.SCAN))
    with log.path.open("a", encoding="utf-8") as file:
        file.write('{"time": "2026-01-02T03:04:05", "mess')  # crash: no line break at the end
    log.load()
    assert [e.message for e in log.entries] == [
        "Scan started",
        "Line 2 in the log is damaged and was skipped",
    ]
    assert log.entries[1].level == LogLevel.WARNING
    assert log.entries[1].category == LogCategory.MISC

    log.write(LogEntry("Project loaded", LogCategory.PROJECT))
    fresh = ProjectLog(log.path)
    fresh.load()
    assert [e.message for e in fresh.entries] == [
        "Scan started",
        "Project loaded",
        "Line 2 in the log is damaged and was skipped",
    ]


@pytest.fixture
def filled(log: ProjectLog) -> ProjectLog:
    """A log with four entries at known times, in memory only."""
    log.entries = [
        LogEntry("Project created", LogCategory.PROJECT, LogLevel.INFO, datetime(2026, 1, 1)),
        LogEntry("Login failed on 192.0.2.11", LogCategory.HOST, LogLevel.SECURITY, datetime(2026, 1, 2)),
        LogEntry("Scan started on 192.0.2.11", LogCategory.SCAN, LogLevel.INFO, datetime(2026, 1, 3)),
        LogEntry("Scan failed on 192.0.2.12", LogCategory.SCAN, LogLevel.ERROR, datetime(2026, 1, 4)),
    ]
    return log


def messages(entries: list[LogEntry]) -> list[str]:
    """Return only the messages, to keep the asserts short."""
    return [entry.message for entry in entries]


def test_find_without_filters_returns_a_copy_of_all(filled: ProjectLog) -> None:
    """No filters means every entry, in a new list that can be changed safely."""
    found = filled.find()
    assert found == filled.entries
    found.clear()
    assert len(filled.entries) == 4


def test_find_by_category(filled: ProjectLog) -> None:
    """Only entries of the category are returned, oldest first."""
    assert messages(filled.find(category=LogCategory.SCAN)) == [
        "Scan started on 192.0.2.11",
        "Scan failed on 192.0.2.12",
    ]


def test_find_by_level(filled: ProjectLog) -> None:
    """Only entries of the level are returned."""
    assert messages(filled.find(level=LogLevel.SECURITY)) == ["Login failed on 192.0.2.11"]


def test_find_since_includes_the_exact_time(filled: ProjectLog) -> None:
    """An entry at exactly the since time is included."""
    assert messages(filled.find(since=datetime(2026, 1, 3))) == [
        "Scan started on 192.0.2.11",
        "Scan failed on 192.0.2.12",
    ]


def test_find_text_ignores_case(filled: ProjectLog) -> None:
    """Text search finds the text anywhere in the message, in any case."""
    assert messages(filled.find(text="LOGIN")) == ["Login failed on 192.0.2.11"]
    assert len(filled.find(text="192.0.2.11")) == 2


def test_find_with_several_filters_needs_all_to_match(filled: ProjectLog) -> None:
    """Filters combine: an entry must match every one given."""
    assert messages(filled.find(category=LogCategory.SCAN, text="192.0.2.11")) == ["Scan started on 192.0.2.11"]


def test_find_with_no_match_returns_empty(filled: ProjectLog) -> None:
    """No match is an empty list, not an error."""
    assert filled.find(level=LogLevel.WARNING) == []
