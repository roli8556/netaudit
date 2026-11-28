"""Project handling, including creation, loading and deletion."""

import json
from enum import Enum
from dataclasses import asdict, dataclass, field
from pathlib import Path
from datetime import datetime

from netaudit.enc_handler import EncHandler
from netaudit.host import Host
from netaudit.log import LogCategory, LogEntry, LogLevel, ProjectLog
from netaudit.scans.scans import SCAN_TYPES, Scan


# The folders every project has. Create makes them, load warns about missing ones.
PROJECT_FOLDERS = ("logs", "configs", "scans")

# The salt and Argon2 settings of a project, in plain JSON: needed to make the key, so it can't be encrypted itself.
SALT_FILE = "project.salt"


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

    def __post_init__(self) -> None:
        """Check the settings. Raises ValueError if one is invalid."""
        # Type checks come first, and type() is not int also rejects True and False (see Host).
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Project name cannot be empty")
        if len(self.name) > 64 or not self.name.isprintable():
            raise ValueError(f"Project name must be at most 64 printable characters, got {self.name!r}")
        if type(self.ssh_port) is not int or not 1 <= self.ssh_port <= 65535:
            raise ValueError(f"SSH port must be a whole number from 1 to 65535, got {self.ssh_port!r}")
        if type(self.ssh_timeout) is not int or not 1 <= self.ssh_timeout <= 300:
            raise ValueError(f"SSH timeout must be a whole number of seconds from 1 to 300, got {self.ssh_timeout!r}")
        if not isinstance(self.created_time, str):
            raise ValueError(f"Created time must be text, got {self.created_time!r}")
        try:
            datetime.strptime(self.created_time, "%Y-%m-%d %H:%M:%S")
        except ValueError as error:
            raise ValueError(f"Created time must look like 2026-01-02 03:04:05, got {self.created_time!r}") from error

    def save(self, path: Path, enc_handler: EncHandler) -> None:
        """Save or create a new project configuration file: JSON, encrypted with enc_handler."""
        text = json.dumps(asdict(self), indent=4)
        token = enc_handler.encrypt(text.encode("utf-8"))
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_bytes(token)
        temp_path.replace(path)

    @staticmethod
    def load(path: Path, enc_handler: EncHandler) -> "ProjectConfig":
        """Load a project configuration file, decrypted with enc_handler.

        Raises ValueError naming the file if it is damaged, and FileNotFoundError if it is missing.
        This is the first file a load decrypts, so if it can't be decrypted, the password is most likely wrong:
        then the ValueError says "Wrong password, or the file is damaged"."""
        token = path.read_bytes()
        decrypted_text = enc_handler.decrypt(token)  # outside the try: a wrong password isn't a damaged file
        try:
            data = json.loads(decrypted_text)  # json.loads also takes bytes
            return ProjectConfig(**data)
        except (ValueError, KeyError, TypeError) as error:  # JSONDecodeError is a ValueError
            raise ValueError(f"{path} is damaged: {error}") from error



@dataclass
class Project:
    """A project is for a single network, and controls most of the netaudit functionality. 
    It is a directory containing multiple files, including a configuration file for the project,
    logs, device configs, and other data."""

    path: Path
    config: ProjectConfig
    enc_handler: EncHandler
    hosts: list[Host] = field(default_factory=list)
    scans: list[Scan] = field(default_factory=list)
    log: ProjectLog = field(init=False)  # made from path in __post_init__, not given by the caller
    issues: dict[ProjectIssue, list[str]] = field(default_factory=dict)  # found by load, cleared when fixed

    def __post_init__(self) -> None:
        """Attach the project's log. This doesn't touch the disk."""
        self.log = ProjectLog(self.path / "logs" / "project.log")

    def save_hosts(self) -> None:
        """Save the hosts, including their passwords, to an encrypted JSON file in the project directory."""
        hosts_path = self.path / "hosts.json"
        text = json.dumps([asdict(host) for host in self.hosts], indent=4)
        token = self.enc_handler.encrypt(text.encode("utf-8"))
        temp_path = hosts_path.with_name(hosts_path.name + ".tmp")
        temp_path.write_bytes(token)
        temp_path.replace(hosts_path)

    def load_hosts(self) -> None:
        """Load the hosts from an encrypted JSON file in the project directory.

        Raises ValueError naming the file if it is damaged, and then self.hosts is unchanged."""
        hosts_path = self.path / "hosts.json"
        if hosts_path.exists():
            token = hosts_path.read_bytes()
            try:
                # Inside the try: config.json was decrypted first, so the password is right and this file is damaged.
                data = json.loads(self.enc_handler.decrypt(token))
                if not isinstance(data, list):
                    raise ValueError("it does not contain a list of hosts")
                hosts = [Host(**host_data) for host_data in data]
                ips = [host.ip for host in hosts]
                if len(ips) != len(set(ips)):  # a set keeps each IP once, so it is shorter if one repeats
                    raise ValueError("it contains the same IP address more than once")
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"{hosts_path} is damaged: {error}") from error
            self.hosts = hosts
        else:
            self.hosts = []

    def add_host(self, host: Host) -> None:
        """Add a host and save the hosts. Raises ValueError if a host with the same IP exists.

        If saving fails, the host is taken out again, so memory and file still match."""
        for existing in self.hosts:
            if existing.ip == host.ip:
                raise ValueError(f"A host with IP {host.ip} already exists")
        self.hosts.append(host)
        try:
            self.save_hosts()
        except OSError:
            self.hosts.remove(host)
            raise
        self.log.write(LogEntry(f"Added host {host.ip}", LogCategory.HOST), self.enc_handler)

    def remove_host(self, ip: str) -> Host:
        """Remove the host with this IP, save the hosts, and return the removed host.

        Raises ValueError if no host has this IP. If saving fails, the host is put back where it was."""
        for index, host in enumerate(self.hosts):
            if host.ip == ip:
                break
        else:
            raise ValueError(f"No host with IP {ip!r}")
        self.hosts.pop(index)
        try:
            self.save_hosts()
        except OSError:
            self.hosts.insert(index, host)
            raise
        self.log.write(LogEntry(f"Removed host {ip}", LogCategory.HOST), self.enc_handler)
        return host

    def load_scans(self) -> None:
        """Load the scans (encrypted JSON files) from the scans directory in the project directory.

        Raises ValueError naming the file if one is damaged, and then self.scans is unchanged."""
        scans_path = self.path / "scans"
        scans = []
        # sorted by file name means oldest first, as the name starts with the time
        for scan_file in sorted(scans_path.glob("*.scan.json")):
            token = scan_file.read_bytes()
            try:
                data = json.loads(self.enc_handler.decrypt(token))  # inside the try, as in load_hosts
                if not isinstance(data, dict):
                    raise ValueError("it does not contain a scan")
                scan_type = data.pop("type")
                performed_at = datetime.fromisoformat(data.pop("performed_at"))
                data["path"] = scan_file  # never trust a path from inside the file
                if scan_type not in SCAN_TYPES:
                    raise ValueError(f"unknown scan type {scan_type!r}")
                scan_class = SCAN_TYPES[scan_type]
                scans.append(scan_class(performed_at=performed_at, **data))
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"{scan_file} is damaged: {error}") from error
        self.scans = scans

    @classmethod
    def create(cls, path: Path, config: ProjectConfig, password: str) -> "Project":
        """Create the project directory, subdirectories, salt file and configuration file, and return the new project.

        The key is made from password, and the password itself is not kept.
        Raises FileExistsError if the directory already exists, and ValueError for an invalid password."""
        path.mkdir(parents=True)
        for folder in PROJECT_FOLDERS:
            (path / folder).mkdir()
        enc_handler = EncHandler.create(path / SALT_FILE, password)
        config.save(path / "config.json", enc_handler)
        project = cls(path, config, enc_handler)
        project.log.write(LogEntry("Project created", LogCategory.PROJECT), project.enc_handler)
        return project

    @classmethod
    def load(cls, path: Path, password: str) -> "Project":
        """Return the project stored in path, with its configuration and any other data, decrypted with password.

        If any part can't be loaded this raises, and no project is returned. A wrong password is a ValueError
        "Wrong password, or the file is damaged", from config.json.
        A missing logs folder is created. Every missing folder is logged as a warning,
        and the others are added to project.issues."""
        enc_handler = EncHandler.load(path / SALT_FILE, password)
        config = ProjectConfig.load(path / "config.json", enc_handler)
        project = cls(path, config, enc_handler)
        project.load_hosts()
        project.load_scans()
        missing = project.missing_folders()
        if "logs" in missing:
            (path / "logs").mkdir()
        project.log.load(project.enc_handler)
        for folder in missing:
            if folder == "logs":
                message = "Folder logs/ was missing and was created"
            else:
                message = f"Folder {folder}/ is missing"
            project.log.write(LogEntry(message, LogCategory.PROJECT, LogLevel.WARNING), project.enc_handler)
        still_missing = [folder for folder in missing if folder != "logs"]
        if still_missing:
            project.issues[ProjectIssue.MISSING_FOLDER] = still_missing
        project.log.write(LogEntry("Project loaded", LogCategory.PROJECT), project.enc_handler)
        # To add: Menu allows for multiple options on how to fix the missing folders
        return project

    def missing_folders(self) -> list[str]:
        """Return the names of the project folders that don't exist, for example ["configs"]."""
        return [folder for folder in PROJECT_FOLDERS if not (self.path / folder).is_dir()]

    def create_missing_folders(self) -> None:
        """Create the project folders that don't exist, log each one, and clear the issue."""
        for folder in self.missing_folders():
            (self.path / folder).mkdir()
            self.log.write(LogEntry(f"Created missing folder {folder}/", LogCategory.PROJECT), self.enc_handler)
        self.issues.pop(ProjectIssue.MISSING_FOLDER, None)  # None: no error if it isn't there
