"""Project handling, including creation, loading and deletion."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from datetime import datetime

from netaudit.host import Host
from netaudit.scans.scans import Scan


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
    #TO ADD: logging object, encryption handler.

    def save_hosts(self) -> None:
        """Save the hosts, without their passwords, to a JSON file in the project directory."""
        hosts_path = self.path / "hosts.json"
        data = [asdict(host) for host in self.hosts]
        for host_data in data:
            # TODO: save the passwords too, once the file is encrypted (part B)
            del host_data["password"]
            del host_data["enable_password"]
        text = json.dumps(data, indent=4)
        temp_path = hosts_path.with_name(hosts_path.name + ".tmp")
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(hosts_path)
        #TO add: encrypt before writing (part B), this is plain text for now

    def load_hosts(self) -> None:
        """Load the hosts from a JSON file in the project directory."""
        hosts_path = self.path / "hosts.json"
        if hosts_path.exists():
            text = hosts_path.read_text(encoding="utf-8")
            data = json.loads(text)
            # passwords aren't saved until part B, so they start out empty
            self.hosts = [Host(**host_data, password="") for host_data in data]
        else:
            self.hosts = []
    def load_scans(self) -> None:
        """Load the scans from the scans directory in the project directory."""
        scans_path = self.path / "scans"
        if scans_path.exists():
            for scan_file in scans_path.iterdir():
                if scan_file.suffix == ".json":
                    text = scan_file.read_text(encoding="utf-8")
                    data = json.loads(text)
                    scan_type = data.pop("type")
                    performed_at = datetime.fromisoformat(data.pop("performed_at"))
                    scan_class = globals()[scan_type]
                    scan = scan_class(performed_at=performed_at, **data)
                    self.scans.append(scan)

    def create_project(self) -> None:
        """Create the project directory, subdirectories, and save the configuration file."""
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "logs").mkdir(exist_ok=True)
        (self.path / "configs").mkdir(exist_ok=True)
        (self.path / "scans").mkdir(exist_ok=True)
        config_path = self.path / "config.json"
        self.config.save(config_path)
    def load_project(self) -> None:
        """Load the project configuration file and any other data."""
        config_path = self.path / "config.json"
        self.config = ProjectConfig.load(config_path)
        self.load_hosts()
        self.load_scans()

