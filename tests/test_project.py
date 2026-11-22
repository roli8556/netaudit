"""Tests for netaudit/project.py."""

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from netaudit import project as project_module
from netaudit.host import Host
from netaudit.project import Project, ProjectConfig
from netaudit.scans.scans import Scan


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
    host = Host("192.0.2.11", "core", "auditor", "fake-login")
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
    project.hosts.append(Host("192.0.2.11", "core", "auditor", "fake-login", "fake-enable"))
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
    project = Project(tmp_path / "bank", ProjectConfig("bank"))
    project.create_project()
    return project


@pytest.fixture
def host() -> Host:
    """A host with fake passwords."""
    return Host("192.0.2.11", "core", "auditor", "fake-login", "fake-enable")


def without_passwords(host: Host) -> Host:
    """The host as it looks after saving and loading."""
    return Host(host.ip, host.hostname, host.username, password="")


def test_create_makes_the_folders_and_config(created: Project) -> None:
    """A new project has its folders and a saved config."""
    for folder in ("logs", "configs", "scans"):
        assert (created.path / folder).is_dir()
    assert ProjectConfig.load(created.path / "config.json") == created.config


def test_hosts_survive_save_and_load(created: Project, host: Host) -> None:
    """Everything but the passwords is restored."""
    no_enable = Host("192.0.2.12", "access", "auditor", "fake-login")
    created.hosts = [host, no_enable]
    created.save_hosts()
    created.hosts = []
    created.load_hosts()
    assert created.hosts == [without_passwords(host), without_passwords(no_enable)]


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
    assert created.hosts == [without_passwords(host)]


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


def test_load_project_restores_config_hosts_and_scans(created: Project, host: Host) -> None:
    """Loading brings back all parts of a project."""
    created.hosts = [host]
    created.save_hosts()
    scan = Scan()
    scan.write(created.path / "scans")

    loaded = Project(created.path, ProjectConfig("placeholder"))
    loaded.load_project()
    assert loaded.config == created.config
    assert loaded.hosts == [without_passwords(host)]
    assert [s.performed_at for s in loaded.scans] == [scan.performed_at]


def test_load_missing_project_raises(tmp_path: Path) -> None:
    """A folder that doesn't exist can't be loaded."""
    project = Project(tmp_path / "missing", ProjectConfig("office"))
    with pytest.raises(FileNotFoundError):
        project.load_project()


# Known bugs. These are expected to fail (xfail). When one is fixed pytest reports it
# as a failure because of strict=True, which is the signal to remove its marker.


def test_saved_hosts_do_not_expose_passwords(created: Project, host: Host) -> None:
    """No file in the project contains a readable password."""
    created.hosts = [host]
    created.save_hosts()
    for file in created.path.rglob("*"):
        if file.is_file():
            assert b"fake-login" not in file.read_bytes()
            assert b"fake-enable" not in file.read_bytes()


def test_save_hosts_keeps_passwords_in_memory(created: Project, host: Host) -> None:
    """Saving only leaves the passwords out of the file, not out of the open project."""
    created.hosts = [host]
    created.save_hosts()
    assert host.password == "fake-login"
    assert host.enable_password == "fake-enable"


def test_create_does_not_overwrite_a_project(created: Project) -> None:
    """Creating where a project already exists leaves that project intact."""
    with pytest.raises(FileExistsError):
        Project(created.path, ProjectConfig("school")).create_project()
    assert ProjectConfig.load(created.path / "config.json").name == "bank"


@pytest.mark.xfail(strict=True, raises=KeyError, reason="globals() doesn't contain scan subclasses")
def test_load_scans_restores_a_subclass(created: Project) -> None:
    """A scan loads as the class that wrote it."""
    FakeHostScan("192.0.2.11").write(created.path / "scans")
    created.load_scans()
    assert isinstance(created.scans[0], FakeHostScan)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="globals() lets the file pick what to call")
def test_scan_file_cannot_call_other_functions(
    created: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The type in a scan file can only ever name a scan class."""
    calls = []
    monkeypatch.setattr(project_module, "helper", lambda **args: calls.append(args), raising=False)
    content = {"type": "helper", "performed_at": "2026-01-02T03:04:05"}
    (created.path / "scans" / "forged.scan.json").write_text(json.dumps(content), encoding="utf-8")
    try:
        created.load_scans()
    except (KeyError, ValueError):
        pass
    assert calls == []


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="load_scans appends to the old list")
def test_load_scans_twice_does_not_duplicate(created: Project) -> None:
    """Loading replaces the list of scans."""
    Scan().write(created.path / "scans")
    created.load_scans()
    created.load_scans()
    assert len(created.scans) == 1


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="path is read from the file's contents")
def test_loaded_scan_path_is_the_file_it_came_from(created: Project) -> None:
    """A scan file can't claim to be located somewhere else."""
    content = {"type": "Scan", "performed_at": "2026-01-02T03:04:05", "path": "somewhere/else"}
    file = created.path / "scans" / "forged.scan.json"
    file.write_text(json.dumps(content), encoding="utf-8")
    created.load_scans()
    assert created.scans[0].path == file


@pytest.mark.xfail(strict=True, raises=KeyError, reason="every .json file is treated as a scan")
def test_load_scans_ignores_other_json_files(created: Project) -> None:
    """Only *.scan.json files are scans."""
    (created.path / "scans" / "notes.json").write_text("{}", encoding="utf-8")
    created.load_scans()
    assert created.scans == []


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="{} is accepted as an empty host list")
def test_load_hosts_rejects_json_that_is_not_a_list(created: Project) -> None:
    """Valid JSON of the wrong shape is an error."""
    (created.path / "hosts.json").write_text("{}", encoding="utf-8")
    try:
        created.load_hosts()
    except ValueError:
        return
    assert False, "{} was accepted"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="a failed load leaves two projects mixed")
def test_failed_load_changes_nothing(created: Project, tmp_path: Path) -> None:
    """If any part can't be loaded, the open project is left as it was."""
    broken = Project(tmp_path / "school", ProjectConfig("school"))
    broken.create_project()
    (broken.path / "hosts.json").write_text("broken", encoding="utf-8")
    created.path = broken.path
    try:
        created.load_project()
    except ValueError:
        pass
    assert created.config.name == "bank"
