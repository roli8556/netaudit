"""Project handling, including creation, loading and deletion."""

import json
from dataclasses import asdict, dataclass, field
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
    
    def save(self, path: Path) -> None:
        """Save or create a new project configuration file in JSON format."""
        # TODO: encrypt before writing (part B), this is plain text for now
        text = json.dumps(asdict(self), indent=4)
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(path)

    @staticmethod
    def load(path: Path) -> "ProjectConfig":
        """Load a project configuration file from JSON format."""
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return ProjectConfig(**data)



@dataclass
class Project:
    """A project is for a single network, and controls most of the netaudit functionality. 
    It is a directory containing multiple files, including a configuration file for the project,
    logs, device configs, and other data."""

    path: Path
    config: ProjectConfig
