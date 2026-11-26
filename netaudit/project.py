"""Project handling, including creation, loading and deletion."""

import json
from enum import Enum
from dataclasses import asdict, dataclass, field
from pathlib import Path
from datetime import datetime

from netaudit.host import Host
from netaudit.log import LogCategory, LogEntry, LogLevel, ProjectLog
from netaudit.scans.scans import SCAN_TYPES, Scan


# The folders every project has. Create makes them, load warns about missing ones.
PROJECT_FOLDERS = ("logs", "configs", "scans")


class ProjectIssue(Enum):
    """A kind of problem a loaded project can have. The menu decides what to do about each one."""

    MISSING_FOLDER = "MISSING_FOLDER"  # details: the names of the missing folders, not logs (load recreates it)


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
    hosts: list[Host] = field(default_factory=list)
    scans: list[Scan] = field(default_factory=list)
    log: ProjectLog = field(init=False)  # made from path in __post_init__, not given by the caller
    issues: dict[ProjectIssue, list[str]] = field(default_factory=dict)  # found by load, cleared when fixed
    #TO ADD: encryption handler.

    def __post_init__(self) -> None:
        """Attach the project's log. This doesn't touch the disk."""
        self.log = ProjectLog(self.path / "logs" / "project.log")

    def save_hosts(self) -> None:
        """Save the hosts, including their passwords, to a JSON file in the project directory."""
        hosts_path = self.path / "hosts.json"
        text = json.dumps([asdict(host) for host in self.hosts], indent=4)
        temp_path = hosts_path.with_name(hosts_path.name + ".tmp")
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(hosts_path)
        self.log.write(LogEntry(f"Saved {len(self.hosts)} hosts", LogCategory.PROJECT))
        #TO add: encrypt before writing (part B), this is plain text for now

    def load_hosts(self) -> None:
        """Load the hosts from a JSON file in the project directory."""
        hosts_path = self.path / "hosts.json"
        if hosts_path.exists():
            text = hosts_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, list):
                raise ValueError(f"{hosts_path} does not contain a list of hosts")
            self.hosts = [Host(**host_data) for host_data in data]
        else:
            self.hosts = []
    def load_scans(self) -> None:
        """Load the scans from the scans directory in the project directory."""
        scans_path = self.path / "scans"
        scans = []
        # sorted by file name means oldest first, as the name starts with the time
        for scan_file in sorted(scans_path.glob("*.scan.json")):
            text = scan_file.read_text(encoding="utf-8")
            data = json.loads(text)
            scan_type = data.pop("type")
            performed_at = datetime.fromisoformat(data.pop("performed_at"))
            data["path"] = scan_file  # never trust a path from inside the file
            if scan_type not in SCAN_TYPES:
                raise ValueError(f"Unknown scan type {scan_type!r} in {scan_file}")
            scan_class = SCAN_TYPES[scan_type]
            scans.append(scan_class(performed_at=performed_at, **data))
        self.scans = scans

    @classmethod
    def create(cls, path: Path, config: ProjectConfig) -> "Project":
        """Create the project directory, subdirectories and configuration file, and return the new project.

        Raises FileExistsError if the directory already exists."""
        path.mkdir(parents=True)
        for folder in PROJECT_FOLDERS:
            (path / folder).mkdir()
        config.save(path / "config.json")
        project = cls(path, config)
        project.log.write(LogEntry("Project created", LogCategory.PROJECT))
        return project

    @classmethod
    def load(cls, path: Path) -> "Project":
        """Return the project stored in path, with its configuration and any other data.

        If any part can't be loaded this raises, and no project is returned.
        A missing logs folder is created. Every missing folder is logged as a warning,
        and the others are added to project.issues."""
        config = ProjectConfig.load(path / "config.json")
        project = cls(path, config)
        project.load_hosts()
        project.load_scans()
        missing = project.missing_folders()
        if "logs" in missing:
            (path / "logs").mkdir()
        project.log.load()
        for folder in missing:
            if folder == "logs":
                message = "Folder logs/ was missing and was created"
            else:
                message = f"Folder {folder}/ is missing"
            project.log.write(LogEntry(message, LogCategory.PROJECT, LogLevel.WARNING))
        still_missing = [folder for folder in missing if folder != "logs"]
        if still_missing:
            project.issues[ProjectIssue.MISSING_FOLDER] = still_missing
        project.log.write(LogEntry("Project loaded", LogCategory.PROJECT))
        # To add: Menu allows for multiple options on how to fix the missing folders
        return project

    def missing_folders(self) -> list[str]:
        """Return the names of the project folders that don't exist, for example ["configs"]."""
        return [folder for folder in PROJECT_FOLDERS if not (self.path / folder).is_dir()]

    def create_missing_folders(self) -> None:
        """Create the project folders that don't exist, log each one, and clear the issue."""
        for folder in self.missing_folders():
            (self.path / folder).mkdir()
            self.log.write(LogEntry(f"Created missing folder {folder}/", LogCategory.PROJECT))
        self.issues.pop(ProjectIssue.MISSING_FOLDER, None)  # None: no error if it isn't there
