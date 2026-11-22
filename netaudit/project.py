"""Project handling, including creation, loading and deletion."""

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime


def current_timestamp() -> str:
    """Return the current local time as text."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ProjectConfig:
    """A project configuration file, which is a JSON file containing the project name and other settings."""
    name: str
    ssh_port: int = 22
    ssh_timeout: int = 10
    created_time: str = field(default_factory=current_timestamp)



@dataclass
class Project:
    """A project is for a single network, and controls most of the netaudit functionality. 
    It is a directory containing multiple files, including a configuration file for the project,
    logs, device configs, and other data."""

    path: Path
    config: ProjectConfig
