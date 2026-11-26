"""Tests for netaudit/project.py."""

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pytest

from netaudit import project as project_module
from netaudit.host import Host
from netaudit.log import LogLevel, ProjectLog
from netaudit.project import Project, ProjectConfig, ProjectIssue
from netaudit.scans.scans import SCAN_TYPES, Scan


def test_config_has_default_settings() -> None:
    """A config only needs a name, the settings have defaults."""
    config = ProjectConfig("office")
    assert config.name == "office"
    assert config.ssh_port == 22
    assert config.ssh_timeout == 10


def test_each_config_gets_its_own_created_time() -> None:
    """The time is taken when a config is created, not when the module is imported."""
    first = ProjectConfig("first")
    time.sleep(1.1)  # the timestamp has a resolution of one second
    second = ProjectConfig("second")
    assert first.created_time != second.created_time


def test_project_stores_path_and_config() -> None:
    """A project keeps the folder and config it was given."""
    config = ProjectConfig("office")
    project = Project(Path("office"), config)
    assert project.path == Path("office")
    assert project.config == config


def test_different_projects_are_not_equal() -> None:
    """Projects are compared by their contents."""
    bank = Project(Path("bank"), ProjectConfig("bank"))
    school = Project(Path("school"), ProjectConfig("school"))
    assert bank != school


def test_projects_do_not_share_hosts() -> None:
    """A host added to one project doesn't appear in another."""
    bank = Project(Path("bank"), ProjectConfig("bank"))
    school = Project(Path("school"), ProjectConfig("school"))
    host = Host("192.0.2.11", "auditor", "fake-login")
    bank.hosts.append(host)
    assert bank.hosts == [host]
    assert school.hosts == []


def test_projects_do_not_share_scans() -> None:
    """A scan added to one project doesn't appear in another."""
    bank = Project(Path("bank"), ProjectConfig("bank"))
    school = Project(Path("school"), ProjectConfig("school"))
    scan = Scan()
    bank.scans.append(scan)
    assert bank.scans == [scan]
    assert school.scans == []


def test_printing_a_project_hides_host_passwords() -> None:
    """Printing a whole project doesn't leak the passwords inside it."""
    project = Project(Path("office"), ProjectConfig("office"))
    project.hosts.append(Host("192.0.2.11", "auditor", "fake-login", enable_password="fake-enable"))
    assert "fake-login" not in repr(project)
    assert "fake-enable" not in repr(project)


def test_save_writes_the_config_as_json(tmp_path: Path) -> None:
    """A saved config contains all its fields."""
    config = ProjectConfig("Västerås")
    path = tmp_path / "config.json"
    config.save(path)
    assert json.loads(path.read_text(encoding="utf-8")) == asdict(config)


def test_save_replaces_an_existing_file(tmp_path: Path) -> None:
    """Saving again overwrites the old config and leaves no temporary file."""
    path = tmp_path / "config.json"
    ProjectConfig("old").save(path)
    ProjectConfig("new").save(path)
    assert json.loads(path.read_text(encoding="utf-8"))["name"] == "new"
    assert list(tmp_path.iterdir()) == [path]


def test_failed_save_keeps_the_old_file(tmp_path: Path) -> None:
    """A config that can't become JSON doesn't damage the file on disk."""
    path = tmp_path / "config.json"
    config = ProjectConfig("office")
    config.save(path)
    old_content = path.read_bytes()
    config.ssh_port = Path("not valid in JSON")
    with pytest.raises(TypeError):
        config.save(path)
    assert path.read_bytes() == old_content


def test_load_returns_the_saved_config(tmp_path: Path) -> None:
    """A config is the same after saving and loading."""
    path = tmp_path / "config.json"
    config = ProjectConfig("office", ssh_port=2222)
    config.save(path)
    assert ProjectConfig.load(path) == config
    assert config.load(path) == config  # a staticmethod also works on an object


def test_save_to_missing_folder_raises(tmp_path: Path) -> None:
    """Save does not create folders."""
    with pytest.raises(FileNotFoundError):
        ProjectConfig("office").save(tmp_path / "missing" / "config.json")


@dataclass
class FakeHostScan(Scan):
    """A minimal subclass, standing in for a real scan."""

    host_ip: str


@pytest.fixture
def created(tmp_path: Path) -> Project:
    """A project that has been created in a temporary folder."""
    return Project.create(tmp_path / "bank", ProjectConfig("bank"))


@pytest.fixture(autouse=True)
def known_fake_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the fake scan a known type, only while each test runs."""
    monkeypatch.setitem(SCAN_TYPES, "FakeHostScan", FakeHostScan)


@pytest.fixture
def host() -> Host:
    """A host with fake passwords."""
    return Host("192.0.2.11", "auditor", "fake-login", enable_password="fake-enable")


def test_create_makes_the_folders_and_config(created: Project) -> None:
    """A new project has its folders and a saved config."""
    for folder in ("logs", "configs", "scans"):
        assert (created.path / folder).is_dir()
    assert ProjectConfig.load(created.path / "config.json") == created.config


def test_hosts_survive_save_and_load(created: Project, host: Host) -> None:
    """All fields are restored, also the passwords and a missing enable password."""
    no_enable = Host("192.0.2.12", "auditor", "fake-login", privilege_level=15)
    created.hosts = [host, no_enable]
    created.save_hosts()
    created.hosts = []
    created.load_hosts()
    assert created.hosts == [host, no_enable]


@pytest.mark.parametrize("commands", [None, [], ["show version", "show vlan"]])
def test_available_commands_survive_save_and_load(
    created: Project, host: Host, commands: list[str] | None
) -> None:
    """Not checked, none available and some available all load back as they were."""
    host.available_commands = commands
    created.hosts = [host]
    created.save_hosts()
    created.load_hosts()
    assert created.hosts[0].available_commands == commands


def test_load_hosts_without_a_file_gives_no_hosts(created: Project, host: Host) -> None:
    """A project without saved hosts has none."""
    created.hosts = [host]
    created.load_hosts()
    assert created.hosts == []


def test_load_hosts_twice_does_not_duplicate(created: Project, host: Host) -> None:
    """Loading replaces the list of hosts."""
    created.hosts = [host]
    created.save_hosts()
    created.load_hosts()
    created.load_hosts()
    assert created.hosts == [host]


def test_load_hosts_rejects_broken_json(created: Project) -> None:
    """A damaged file is an error, not an empty project."""
    (created.path / "hosts.json").write_text("broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        created.load_hosts()


def test_load_scans_restores_a_base_scan(created: Project) -> None:
    """A saved scan gets its time back."""
    scan = Scan()
    scan.write(created.path / "scans")
    created.load_scans()
    assert [loaded.performed_at for loaded in created.scans] == [scan.performed_at]


def test_load_scans_without_a_folder_gives_no_scans(tmp_path: Path) -> None:
    """A missing scans folder is not an error."""
    project = Project(tmp_path, ProjectConfig("office"))
    project.load_scans()
    assert project.scans == []


def test_load_restores_config_hosts_and_scans(created: Project, host: Host) -> None:
    """Loading brings back all parts of a project."""
    created.hosts = [host]
    created.save_hosts()
    scan = Scan()
    scan.write(created.path / "scans")

    loaded = Project.load(created.path)
    assert loaded.config == created.config
    assert loaded.hosts == [host]
    assert [s.performed_at for s in loaded.scans] == [scan.performed_at]


def test_load_missing_project_raises(tmp_path: Path) -> None:
    """A folder that doesn't exist can't be loaded."""
    with pytest.raises(FileNotFoundError):
        Project.load(tmp_path / "missing")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="not encrypted until part B")
def test_saved_hosts_do_not_expose_passwords(created: Project, host: Host) -> None:
    """No file in the project contains a readable password."""
    created.hosts = [host]
    created.save_hosts()
    for file in created.path.rglob("*"):
        if file.is_file():
            assert b"fake-login" not in file.read_bytes()
            assert b"fake-enable" not in file.read_bytes()


def test_create_does_not_overwrite_a_project(created: Project) -> None:
    """Creating where a project already exists leaves that project intact."""
    with pytest.raises(FileExistsError):
        Project.create(created.path, ProjectConfig("school"))
    assert ProjectConfig.load(created.path / "config.json").name == "bank"


def test_load_scans_restores_a_subclass(created: Project) -> None:
    """A scan loads as the class that wrote it."""
    FakeHostScan("192.0.2.11").write(created.path / "scans")
    created.load_scans()
    assert isinstance(created.scans[0], FakeHostScan)


def test_scan_file_cannot_call_other_functions(
    created: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The type in a scan file can only ever name a scan class."""
    calls = []
    monkeypatch.setattr(project_module, "helper", lambda **args: calls.append(args), raising=False)
    content = {"type": "helper", "performed_at": "2026-01-02T03:04:05"}
    (created.path / "scans" / "forged.scan.json").write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError):
        created.load_scans()
    assert calls == []


def test_load_scans_twice_does_not_duplicate(created: Project) -> None:
    """Loading replaces the list of scans."""
    Scan().write(created.path / "scans")
    created.load_scans()
    created.load_scans()
    assert len(created.scans) == 1


def test_loaded_scan_path_is_the_file_it_came_from(created: Project) -> None:
    """A scan file can't claim to be located somewhere else."""
    content = {"type": "Scan", "performed_at": "2026-01-02T03:04:05", "path": "somewhere/else"}
    file = created.path / "scans" / "forged.scan.json"
    file.write_text(json.dumps(content), encoding="utf-8")
    created.load_scans()
    assert created.scans[0].path == file


def test_load_scans_returns_oldest_first(created: Project) -> None:
    """Scans are in the order they were performed."""
    older = FakeHostScan("192.0.2.11", performed_at=datetime(2025, 1, 1))
    newer = Scan(performed_at=datetime(2026, 1, 1))
    newer.write(created.path / "scans")
    older.write(created.path / "scans")
    created.load_scans()
    assert created.scans == [older, newer]


def test_load_scans_ignores_other_json_files(created: Project) -> None:
    """Only *.scan.json files are scans."""
    (created.path / "scans" / "notes.json").write_text("{}", encoding="utf-8")
    created.load_scans()
    assert created.scans == []


@pytest.mark.parametrize("content", ["{}", '""', "5", "null"])
def test_load_hosts_rejects_json_that_is_not_a_list(created: Project, content: str) -> None:
    """Valid JSON of the wrong shape is an error."""
    (created.path / "hosts.json").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        created.load_hosts()


def test_failed_load_changes_nothing(created: Project, host: Host, tmp_path: Path) -> None:
    """If any part can't be loaded, the open project is left as it was."""
    broken = Project.create(tmp_path / "school", ProjectConfig("school"))
    (broken.path / "hosts.json").write_text("broken", encoding="utf-8")
    created.hosts = [host]
    with pytest.raises(ValueError):
        created = Project.load(broken.path)
    assert created.path == tmp_path / "bank"
    assert created.config.name == "bank"
    assert created.hosts == [host]


def test_new_project_has_a_log_but_no_file(tmp_path: Path) -> None:
    """Making a Project object attaches its log without touching the disk."""
    project = Project(tmp_path, ProjectConfig("office"))
    assert project.log.path == tmp_path / "logs" / "project.log"
    assert project.log.entries == []
    assert not project.log.path.exists()


def test_create_logs_that_the_project_was_created(created: Project) -> None:
    """The first entry of a new project is its creation, in memory and in the file."""
    assert [e.message for e in created.log.entries] == ["Project created"]
    fresh = ProjectLog(created.log.path)
    fresh.load()
    assert fresh.entries == created.log.entries


def test_load_reads_the_log_and_logs_the_load(created: Project) -> None:
    """Loading brings back earlier entries and adds one for this load."""
    loaded = Project.load(created.path)
    assert [e.message for e in loaded.log.entries] == ["Project created", "Project loaded"]


def test_failed_load_does_not_write_to_the_log(created: Project) -> None:
    """A project that can't be loaded isn't logged as loaded."""
    (created.path / "hosts.json").write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        Project.load(created.path)
    created.log.load()
    assert [e.message for e in created.log.entries] == ["Project created"]


def test_new_project_is_missing_no_folders(created: Project) -> None:
    """Create makes every project folder."""
    assert created.missing_folders() == []


def test_missing_folders_are_listed(created: Project) -> None:
    """Only the folders that don't exist are returned."""
    (created.path / "configs").rmdir()
    (created.path / "scans").rmdir()
    assert created.missing_folders() == ["configs", "scans"]


def test_load_recreates_logs_and_warns(created: Project) -> None:
    """A project without its logs folder still loads, and the log says what happened."""
    for file in (created.path / "logs").iterdir():
        file.unlink()
    (created.path / "logs").rmdir()
    loaded = Project.load(created.path)
    assert (created.path / "logs").is_dir()
    assert [e.message for e in loaded.log.entries] == [
        "Folder logs/ was missing and was created",
        "Project loaded",
    ]
    assert loaded.log.entries[0].level == LogLevel.WARNING


def test_load_warns_about_other_missing_folders_without_creating_them(created: Project) -> None:
    """Folders other than logs are only reported. Creating them is the user's choice."""
    (created.path / "scans").rmdir()
    loaded = Project.load(created.path)
    assert not (created.path / "scans").exists()
    assert loaded.log.entries[-2].message == "Folder scans/ is missing"
    assert loaded.log.entries[-2].level == LogLevel.WARNING


def test_load_of_a_folder_that_is_not_a_project_creates_nothing(tmp_path: Path) -> None:
    """Without config.json, load fails before it creates any folder."""
    with pytest.raises(FileNotFoundError):
        Project.load(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_create_missing_folders_creates_and_logs_them(created: Project) -> None:
    """After creating, nothing is missing, and the log names each created folder."""
    (created.path / "configs").rmdir()
    (created.path / "scans").rmdir()
    created.create_missing_folders()
    assert created.missing_folders() == []
    assert [e.message for e in created.log.entries[-2:]] == [
        "Created missing folder configs/",
        "Created missing folder scans/",
    ]


def test_create_missing_folders_with_nothing_missing_does_nothing(created: Project) -> None:
    """No folders to create means no log entries either."""
    before = list(created.log.entries)
    created.create_missing_folders()
    assert created.log.entries == before


def test_new_and_complete_project_has_no_issues(created: Project) -> None:
    """Nothing is wrong with a project that was just created, or loaded with all its folders."""
    assert created.issues == {}
    assert Project.load(created.path).issues == {}


def test_load_reports_missing_folders_as_an_issue(created: Project) -> None:
    """The menu can see which folders are missing without reading the log."""
    (created.path / "configs").rmdir()
    (created.path / "scans").rmdir()
    loaded = Project.load(created.path)
    assert loaded.issues == {ProjectIssue.MISSING_FOLDER: ["configs", "scans"]}


def test_recreated_logs_folder_is_not_an_issue(created: Project) -> None:
    """Load fixes a missing logs folder itself, so nothing is left to decide."""
    for file in (created.path / "logs").iterdir():
        file.unlink()
    (created.path / "logs").rmdir()
    assert Project.load(created.path).issues == {}


def test_create_missing_folders_clears_the_issue(created: Project) -> None:
    """Once the folders exist, the issue is gone."""
    (created.path / "scans").rmdir()
    loaded = Project.load(created.path)
    loaded.create_missing_folders()
    assert loaded.issues == {}
