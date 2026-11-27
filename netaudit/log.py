"""The project log: what netaudit did and when. Findings are not logged here, only summaries."""

import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path


class LogLevel(Enum):
    """How serious a logged event is."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SECURITY = "SECURITY"  # failed logins, wrong project password, config changes


class LogCategory(Enum):
    """Which part of netaudit a logged event came from."""

    PROJECT = "PROJECT" # General project events, like creation, opening, closing, saving
    HOST = "HOST" # Events related to a single host, like login failures, config changes, or unreachable hosts
    SCAN = "SCAN"  # collecting data from devices
    CHECK = "CHECK"  # checking collected data for problems
    MISC = "MISC" # Other events that don't fit into the above categories, like errors in the log itself


class LogOrder(Enum):
    """How to sort log entries."""

    NUMBER = "NUMBER"
    TIME = "TIME"


@dataclass
class LogEntry:
    """One event in the log."""

    message: str
    category: LogCategory
    level: LogLevel = LogLevel.INFO
    time: datetime = field(default_factory=datetime.now)
    number: int | None = None  # given by ProjectLog.write, None until the entry is in the file

    def to_line(self) -> str:
        """Return the entry as one line of JSON, without a line break at the end.

        json.dumps escapes line breaks inside the message, so a message can't fake an extra entry."""
        data = {
            "number": self.number,
            "time": self.time.isoformat(),
            "category": self.category.value,
            "level": self.level.value,
            "message": self.message,
        }
        return json.dumps(data)

    @classmethod
    def from_line(cls, line: str) -> "LogEntry":
        """Return the entry stored in one line of JSON.

        Raises ValueError for an unknown category or level, a number that isn't a whole number,
        or a line that isn't JSON."""
        data = json.loads(line)
        if not isinstance(data["number"], int):
            raise ValueError(f"Log entry number is not a whole number: {data['number']!r}")
        return cls(
            message=data["message"],
            category=LogCategory(data["category"]),
            level=LogLevel(data["level"]),
            time=datetime.fromisoformat(data["time"]),
            number=data["number"],
        )


@dataclass
class LogFilter:
    """What to look for in the log, chosen in the log menu. None means any.

    The fields are the same as ProjectLog.find's, and the menu passes them to it.
    The order isn't here: it doesn't remove entries."""

    level: LogLevel | None = None
    category: LogCategory | None = None
    text: str | None = None
    since: datetime | None = None
    from_number: int | None = None
    to_number: int | None = None

    def get_filters(self) -> str:
        """Return the filters that are set, like "level: WARNING, text: '192'", or "" when none are set."""
        parts = []
        if self.level is not None:
            parts.append(f"level: {self.level.value}")
        if self.category is not None:
            parts.append(f"category: {self.category.value}")
        if self.text is not None:
            parts.append(f"text: {self.text!r}")  # quotes show spaces, repr escapes control characters
        if self.since is not None:
            parts.append(f"since: {self.since.strftime('%Y-%m-%d %H:%M')}")
        if self.from_number is not None or self.to_number is not None:
            # A missing end shows as nothing: "10-" is from 10, "-50" is up to 50.
            start = str(self.from_number) if self.from_number is not None else ""
            end = str(self.to_number) if self.to_number is not None else ""
            parts.append(f"numbers: {start}-{end}")
        return ", ".join(parts)


@dataclass
class ProjectLog:
    """Main Log handler,All entries of a project's log, kept in memory and in the log file.

    Never log secrets: no passwords, and never the result of asdict() on a Host.
    Only one netaudit may have a project open, or the entries in memory and the file drift apart."""

    path: Path
    entries: list[LogEntry] = field(default_factory=list)
    _last_number: int = field(default=0, init=False)  # highest number in the file, set by load and write

    def load(self) -> None:
        """Read all entries from the file into self.entries. A missing file means no entries.

        A damaged line (for example half written when netaudit crashed) is skipped, and a warning
        about it is added to self.entries only, not to the file, so loading never changes the file."""
        if not self.path.exists():
            self.entries = []
            self._last_number = 0
            return
        entries = []
        damaged = []
        text = self.path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entries.append(LogEntry.from_line(line))
            except (ValueError, KeyError, TypeError):
                damaged.append(number)
        # max, not the last entry: if lines were moved around, the last one isn't the highest
        self._last_number = max((entry.number for entry in entries), default=0)
        for number in damaged:
            message = f"Line {number} in the log is damaged and was skipped"
            entries.append(LogEntry(message, LogCategory.MISC, LogLevel.WARNING))
        self.entries = entries

    def write(self, entry: LogEntry) -> None:
        """Give the entry the next number, add it to the end of the file, then to self.entries.

        Create the entry right before writing it, so its time is when it happened.
        Raises FileNotFoundError if the folder doesn't exist, and then the entry and self.entries are unchanged."""
        number = self._last_number + 1
        line = replace(entry, number=number).to_line() + "\n"  # a copy, so a failed write leaves entry as it was
        if self._ends_with_half_line():
            line = "\n" + line  # don't glue the new entry onto a damaged line
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line)
        entry.number = number
        self._last_number = number
        self.entries.append(entry)

    def find(
        self,
        category: LogCategory | None = None,
        level: LogLevel | None = None,
        since: datetime | None = None,
        text: str | None = None,
        from_number: int | None = None,
        to_number: int | None = None,
    ) -> list[LogEntry]:
        """Return a new list of the entries that match every filter given, oldest first. None means any.

        since: only entries at or after this time. text: only entries whose message contains it,
        ignoring upper and lower case. from_number and to_number: only entries numbered in that range,
        both included. An entry without a number never matches a number filter.
        Only reads the entries in memory, never the file."""
        result = []
        for entry in self.entries:
            if category is not None and entry.category != category:
                continue
            if level is not None and entry.level != level:
                continue
            if since is not None and entry.time < since:
                continue
            if text is not None and text.lower() not in entry.message.lower():
                continue
            if from_number is not None and (entry.number is None or entry.number < from_number):
                continue
            if to_number is not None and (entry.number is None or entry.number > to_number):
                continue
            result.append(entry)
        return result

    @staticmethod
    def sort_entries(
        entries: list[LogEntry], order: LogOrder = LogOrder.NUMBER, newest_first: bool = False
    ) -> list[LogEntry]:
        """Return a new list of the entries sorted by number or time. The given list is not changed.

        Entries without a number (warnings about damaged lines) go last when sorting by number.
        Entries with the same time keep their order."""
        if order == LogOrder.TIME:
            return sorted(entries, key=lambda entry: entry.time, reverse=newest_first)
        numbered = [entry for entry in entries if entry.number is not None]
        unnumbered = [entry for entry in entries if entry.number is None]
        return sorted(numbered, key=lambda entry: entry.number, reverse=newest_first) + unnumbered

    def _ends_with_half_line(self) -> bool:
        """Return True if the file doesn't end with a line break, as after an interrupted write."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return False
        with self.path.open("rb") as file:
            file.seek(-1, 2)  # 2 = count from the end: go to the last byte
            return file.read(1) != b"\n"
