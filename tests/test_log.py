"""Tests for netaudit/log.py."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from netaudit.log import LogCategory, LogEntry, LogFilter, LogLevel, LogOrder, ProjectLog


def test_entry_defaults_to_info_and_now() -> None:
    """Level and time don't have to be given."""
    before = datetime.now()
    entry = LogEntry("Project created", LogCategory.PROJECT)
    assert entry.level == LogLevel.INFO
    assert before <= entry.time <= datetime.now()


def test_entry_survives_a_round_trip() -> None:
    """An entry turned into a line and back is the same entry."""
    entry = LogEntry("Login failed", LogCategory.HOST, LogLevel.SECURITY, datetime(2026, 1, 2, 3, 4, 5), 7)
    assert LogEntry.from_line(entry.to_line()) == entry


def test_line_break_in_message_stays_on_one_line() -> None:
    """A message can't fake an extra entry in the log file."""
    message = 'SW1\n{"level": "INFO", "message": "fake"}'
    line = LogEntry(message, LogCategory.SCAN, number=1).to_line()
    assert "\n" not in line
    assert LogEntry.from_line(line).message == message


@pytest.mark.parametrize("key, value", [("level", "DEBUG"), ("category", "OTHER")])
def test_unknown_level_or_category_raises(key: str, value: str) -> None:
    """Only the values in the enums are accepted."""
    data = json.loads(LogEntry("x", LogCategory.MISC, number=1).to_line())
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


def test_line_without_a_whole_number_raises() -> None:
    """Every line in the file has a number, and only a whole number is accepted."""
    for number in (None, "5", 1.5):
        line = json.dumps({"number": number, "time": "2026-01-02T03:04:05", "category": "MISC",
                           "level": "INFO", "message": "x"})
        with pytest.raises(ValueError):
            LogEntry.from_line(line)


def test_write_numbers_entries_from_one(log: ProjectLog) -> None:
    """The log gives each written entry the next number."""
    first = LogEntry("Project created", LogCategory.PROJECT)
    second = LogEntry("Project loaded", LogCategory.PROJECT)
    assert first.number is None
    log.write(first)
    log.write(second)
    assert (first.number, second.number) == (1, 2)


def test_numbers_continue_after_a_reload(log: ProjectLog) -> None:
    """A fresh log continues from the highest number in the file."""
    log.write(LogEntry("Project created", LogCategory.PROJECT))
    log.write(LogEntry("Project loaded", LogCategory.PROJECT))
    fresh = ProjectLog(log.path)
    fresh.load()
    entry = LogEntry("Project loaded", LogCategory.PROJECT)
    fresh.write(entry)
    assert [e.number for e in fresh.entries] == [1, 2, 3]


def test_damaged_line_does_not_shift_numbers(log: ProjectLog) -> None:
    """The numbers come from the file, not from counting entries, and the warning has no number."""
    log.write(LogEntry("Scan started", LogCategory.SCAN))
    log.write(LogEntry("Scan finished", LogCategory.SCAN))
    lines = log.path.read_text(encoding="utf-8").splitlines()
    log.path.write_text("damaged\n" + lines[1] + "\n", encoding="utf-8")  # entry 1 is damaged
    log.load()
    assert [e.number for e in log.entries] == [2, None]
    log.write(LogEntry("Project loaded", LogCategory.PROJECT))
    assert log.entries[-1].number == 3


def test_failed_write_leaves_the_entry_without_a_number(tmp_path: Path) -> None:
    """An entry that never reached the file doesn't get a number."""
    log = ProjectLog(tmp_path / "missing" / "project.log")
    entry = LogEntry("Project created", LogCategory.PROJECT)
    with pytest.raises(FileNotFoundError):
        log.write(entry)
    assert entry.number is None


@pytest.fixture
def numbered(log: ProjectLog) -> ProjectLog:
    """A log with entries numbered 1 to 5, and one warning without a number, in memory only."""
    log.entries = [LogEntry(f"Entry {n}", LogCategory.MISC, number=n) for n in range(1, 6)]
    log.entries.append(LogEntry("Line 9 in the log is damaged and was skipped", LogCategory.MISC, LogLevel.WARNING))
    return log


def test_find_from_number(numbered: ProjectLog) -> None:
    """from_number includes that number and everything after it."""
    assert [e.number for e in numbered.find(from_number=4)] == [4, 5]


def test_find_to_number(numbered: ProjectLog) -> None:
    """to_number includes that number and everything before it."""
    assert [e.number for e in numbered.find(to_number=2)] == [1, 2]


def test_find_number_range_and_exact_number(numbered: ProjectLog) -> None:
    """Both together give a range, and the same number twice gives one entry."""
    assert [e.number for e in numbered.find(from_number=2, to_number=4)] == [2, 3, 4]
    assert [e.number for e in numbered.find(from_number=3, to_number=3)] == [3]


def test_find_without_number_filter_includes_unnumbered(numbered: ProjectLog) -> None:
    """Entries without a number are only left out when filtering on numbers."""
    assert len(numbered.find()) == 6
    assert len(numbered.find(from_number=1)) == 5


def test_next_number_follows_the_highest_even_out_of_order(log: ProjectLog) -> None:
    """If lines were moved around, the next number is still one above the highest."""
    for number in (1, 3, 2):
        line = LogEntry(f"Entry {number}", LogCategory.MISC, number=number).to_line()
        with log.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
    log.load()
    entry = LogEntry("Project loaded", LogCategory.PROJECT)
    log.write(entry)
    assert entry.number == 4


def test_failed_write_does_not_use_up_a_number(log: ProjectLog, tmp_path: Path) -> None:
    """After a failed write, the next successful one gets the number the failed one would have had."""
    log.write(LogEntry("Project created", LogCategory.PROJECT))
    real_path = log.path
    log.path = tmp_path / "missing" / "project.log"
    with pytest.raises(FileNotFoundError):
        log.write(LogEntry("Lost", LogCategory.MISC))
    log.path = real_path
    entry = LogEntry("Project loaded", LogCategory.PROJECT)
    log.write(entry)
    assert entry.number == 2


@pytest.fixture
def unsorted() -> list[LogEntry]:
    """Entries out of order by number and by time, plus one without a number."""
    return [
        LogEntry("b", LogCategory.MISC, time=datetime(2026, 1, 3), number=2),
        LogEntry("warning", LogCategory.MISC, LogLevel.WARNING, time=datetime(2026, 1, 9)),
        LogEntry("c", LogCategory.MISC, time=datetime(2026, 1, 1), number=3),
        LogEntry("a", LogCategory.MISC, time=datetime(2026, 1, 2), number=1),
    ]


def test_sort_by_number_puts_unnumbered_last(unsorted: list[LogEntry]) -> None:
    """Sorting by number is the default, and entries without a number come last."""
    assert messages(ProjectLog.sort_entries(unsorted)) == ["a", "b", "c", "warning"]


def test_sort_by_number_newest_first(unsorted: list[LogEntry]) -> None:
    """Newest first reverses the numbered entries, and unnumbered ones still come last."""
    assert messages(ProjectLog.sort_entries(unsorted, newest_first=True)) == ["c", "b", "a", "warning"]


def test_sort_by_time(unsorted: list[LogEntry]) -> None:
    """Sorting by time uses every entry's time, numbered or not."""
    assert messages(ProjectLog.sort_entries(unsorted, LogOrder.TIME)) == ["c", "a", "b", "warning"]
    assert messages(ProjectLog.sort_entries(unsorted, LogOrder.TIME, newest_first=True)) == ["warning", "b", "a", "c"]


def test_sort_by_time_keeps_order_of_equal_times() -> None:
    """Two entries at the same time stay in the order they were given."""
    same = datetime(2026, 1, 1)
    entries = [LogEntry("first", LogCategory.MISC, time=same), LogEntry("second", LogCategory.MISC, time=same)]
    assert messages(ProjectLog.sort_entries(entries, LogOrder.TIME)) == ["first", "second"]


def test_sort_does_not_change_the_given_list(unsorted: list[LogEntry]) -> None:
    """The result is a new list, the original keeps its order."""
    before = list(unsorted)
    ProjectLog.sort_entries(unsorted)
    assert unsorted == before


def test_new_filter_has_nothing_set() -> None:
    """A new LogFilter filters nothing, so describe returns an empty string."""
    filters = LogFilter()
    assert filters == LogFilter(None, None, None, None, None, None)
    assert filters.describe() == ""


@pytest.mark.parametrize(
    "filters, expected",
    [
        (LogFilter(level=LogLevel.WARNING), "level: WARNING"),
        (LogFilter(category=LogCategory.HOST), "category: HOST"),
        (LogFilter(text="192.0.2"), "text: '192.0.2'"),
        (LogFilter(text="admin "), "text: 'admin '"),  # the quotes show the space
        (LogFilter(text="a\nb"), r"text: 'a\nb'"),  # a line break can't break the title
        (LogFilter(since=datetime(2026, 11, 27, 14, 5, 59)), "since: 2026-11-27 14:05"),
        (LogFilter(from_number=10, to_number=50), "numbers: 10-50"),
        (LogFilter(from_number=10), "numbers: 10-"),
        (LogFilter(to_number=50), "numbers: -50"),
    ],
)
def test_filter_describes_one_field(filters: LogFilter, expected: str) -> None:
    """Each field that is set is described on its own."""
    assert filters.describe() == expected


def test_filter_describes_all_fields_in_order() -> None:
    """With every field set, the parts come in field order, separated by commas."""
    filters = LogFilter(
        LogLevel.ERROR, LogCategory.SCAN, "ssh", datetime(2026, 11, 27, 9, 0), from_number=1, to_number=9
    )
    assert filters.describe() == "level: ERROR, category: SCAN, text: 'ssh', since: 2026-11-27 09:00, numbers: 1-9"
