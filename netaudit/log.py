"""The project log: what netaudit did and when. Findings are not logged here, only summaries."""

import json
from dataclasses import dataclass, field
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


@dataclass
class LogEntry:
    """One event in the log."""

    message: str
    category: LogCategory
    level: LogLevel = LogLevel.INFO
    time: datetime = field(default_factory=datetime.now)

    def to_line(self) -> str:
        """Return the entry as one line of JSON, without a line break at the end.

        json.dumps escapes line breaks inside the message, so a message can't fake an extra entry."""
        data = {
            "time": self.time.isoformat(),
            "category": self.category.value,
            "level": self.level.value,
            "message": self.message,
        }
        return json.dumps(data)

    @classmethod
    def from_line(cls, line: str) -> "LogEntry":
        """Return the entry stored in one line of JSON.

        Raises ValueError for an unknown category or level, or a line that isn't JSON."""
        data = json.loads(line)
        return cls(
            message=data["message"],
            category=LogCategory(data["category"]),
            level=LogLevel(data["level"]),
            time=datetime.fromisoformat(data["time"]),
        )


@dataclass
class ProjectLog:
    """Main Log handler,All entries of a project's log, kept in memory and in the log file.

    Never log secrets: no passwords, and never the result of asdict() on a Host.
    Only one netaudit may have a project open, or the entries in memory and the file drift apart."""

    path: Path
    entries: list[LogEntry] = field(default_factory=list)

    def load(self) -> None:
        """Read all entries from the file into self.entries. A missing file means no entries.

        A damaged line (for example half written when netaudit crashed) is skipped, and a warning
        about it is added to self.entries only, not to the file, so loading never changes the file."""
        if not self.path.exists():
            self.entries = []
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
        for number in damaged:
            message = f"Line {number} in the log is damaged and was skipped"
            entries.append(LogEntry(message, LogCategory.MISC, LogLevel.WARNING))
        self.entries = entries

    def write(self, entry: LogEntry) -> None:
        """Add an entry to the end of the file, then to self.entries.

        Create the entry right before writing it, so its time is when it happened.
        Raises FileNotFoundError if the folder doesn't exist, and then self.entries is unchanged."""
        line = entry.to_line() + "\n"
        if self._ends_with_half_line():
            line = "\n" + line  # don't glue the new entry onto a damaged line
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line)
        self.entries.append(entry)

    def find(
        self,
        category: LogCategory | None = None,
        level: LogLevel | None = None,
        since: datetime | None = None,
        text: str | None = None,
    ) -> list[LogEntry]:
        """Return a new list of the entries that match every filter given, oldest first. None means any.

        since: only entries at or after this time. text: only entries whose message contains it,
        ignoring upper and lower case. Only reads the entries in memory, never the file."""
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
            result.append(entry)
        return result

    def _ends_with_half_line(self) -> bool:
        """Return True if the file doesn't end with a line break, as after an interrupted write."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return False
        with self.path.open("rb") as file:
            file.seek(-1, 2)  # 2 = count from the end: go to the last byte
            return file.read(1) != b"\n"
