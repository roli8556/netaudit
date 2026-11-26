"""The project log: what netaudit did and when. Findings are not logged here, only summaries."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    """How serious a logged event is."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SECURITY = "SECURITY"  # failed logins, wrong project password, config changes


class LogCategory(Enum):
    """Which part of netaudit a logged event came from."""

    PROJECT = "PROJECT"
    HOST = "HOST"
    SCAN = "SCAN"  # collecting data from devices
    CHECK = "CHECK"  # checking collected data for problems
    MISC = "MISC"


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
