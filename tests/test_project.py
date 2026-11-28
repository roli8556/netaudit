"""Tests for netaudit/project.py."""

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pytest

from conftest import PROJECT_PASSWORD
from netaudit import project as project_module
from netaudit.enc_handler import EncHandler
from netaudit.host import Host
from netaudit.log import LogLevel, ProjectLog
from netaudit.project import SALT_FILE, Project, ProjectConfig, ProjectIssue
from netaudit.scans.scans import SCAN_TYPES, Scan


# Every test in this file creates projects with tiny Argon2 settings (see conftest.py).
pytestmark = pytest.mark.usefixtures("fast_argon2")


def write_encrypted(path: Path, text: str, enc_handler: EncHandler) -> None:
    """Write text to path encrypted, as netaudit does, to test what load does with its content."""
    path.write_bytes(enc_handler.encrypt(text.encode("utf-8")))


def read_decrypted(path: Path, enc_handler: EncHandler) -> str:
    """Return the decrypted text of a file netaudit wrote."""
    return enc_handler.decrypt(path.read_bytes()).decode("utf-8")


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


def test_project_stores_path_and_config(enc_handler: EncHandler) -> None:
    """A project keeps the folder and config it was given."""
    config = ProjectConfig("office")
    project = Project(Path("office"), config, enc_handler)
    assert project.path == Path("office")
    assert project.config == config
    assert project.enc_handler is enc_handler


def test_different_projects_are_not_equal(enc_handler: EncHandler) -> None:
    """Projects are compared by their contents."""
    bank = Project(Path("bank"), ProjectConfig("bank"), enc_handler)
    school = Project(Path("school"), ProjectConfig("school"), enc_handler)
    assert bank != school


def test_projects_do_not_share_hosts(enc_handler: EncHandler) -> None:
    """A host added to one project doesn't appear in another."""
    bank = Project(Path("bank"), ProjectConfig("bank"), enc_handler)
    school = Project(Path("school"), ProjectConfig("school"), enc_handler)
    host = Host("192.0.2.11", "auditor", "fake-login")
    bank.hosts.append(host)
    assert bank.hosts == [host]
    assert school.hosts == []


def test_projects_do_not_share_scans(enc_handler: EncHandler) -> None:
    """A scan added to one project doesn't appear in another."""
    bank = Project(Path("bank"), ProjectConfig("bank"), enc_handler)
    school = Project(Path("school"), ProjectConfig("school"), enc_handler)
    scan = Scan()
    bank.scans.append(scan)
    assert bank.scans == [scan]
    assert school.scans == []


def test_printing_a_project_hides_host_passwords(enc_handler: EncHandler) -> None:
    """Printing a whole project doesn't leak the passwords inside it."""
    project = Project(Path("office"), ProjectConfig("office"), enc_handler)
    project.hosts.append(Host("192.0.2.11", "auditor", "fake-login", enable_password="fake-enable"))
    assert "fake-login" not in repr(project)
    assert "fake-enable" not in repr(project)


def test_save_writes_the_config_as_json(tmp_path: Path, enc_handler: EncHandler) -> None:
    """A saved config contains all its fields, and none of them can be read without the key."""
    config = ProjectConfig("Västerås")
    path = tmp_path / "config.enc"
    config.save(path, enc_handler)
    assert json.loads(read_decrypted(path, enc_handler)) == asdict(config)
    assert "Västerås".encode("utf-8") not in path.read_bytes()


def test_save_replaces_an_existing_file(tmp_path: Path, enc_handler: EncHandler) -> None:
    """Saving again overwrites the old config and leaves no temporary file."""
    path = tmp_path / "config.enc"
    ProjectConfig("old").save(path, enc_handler)
    ProjectConfig("new").save(path, enc_handler)
    assert json.loads(read_decrypted(path, enc_handler))["name"] == "new"
    assert list(tmp_path.iterdir()) == [path]


def test_failed_save_keeps_the_old_file(tmp_path: Path, enc_handler: EncHandler) -> None:
    """A config that can't become JSON doesn't damage the file on disk."""
    path = tmp_path / "config.enc"
    config = ProjectConfig("office")
    config.save(path, enc_handler)
    old_content = path.read_bytes()
    config.ssh_port = Path("not valid in JSON")
    with pytest.raises(TypeError):
        config.save(path, enc_handler)
    assert path.read_bytes() == old_content


def test_load_returns_the_saved_config(tmp_path: Path, enc_handler: EncHandler) -> None:
    """A config is the same after saving and loading."""
    path = tmp_path / "config.enc"
    config = ProjectConfig("office", ssh_port=2222)
    config.save(path, enc_handler)
    assert ProjectConfig.load(path, enc_handler) == config
    assert config.load(path, enc_handler) == config  # a staticmethod also works on an object


def test_save_to_missing_folder_raises(tmp_path: Path, enc_handler: EncHandler) -> None:
    """Save does not create folders."""
    with pytest.raises(FileNotFoundError):
        ProjectConfig("office").save(tmp_path / "missing" / "config.enc", enc_handler)


@dataclass
class FakeHostScan(Scan):
    """A minimal subclass, standing in for a real scan."""

    host_ip: str


@pytest.fixture
def created(tmp_path: Path) -> Project:
    """A project that has been created in a temporary folder."""
    return Project.create(tmp_path / "bank", ProjectConfig("bank"), PROJECT_PASSWORD)


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
    assert ProjectConfig.load(created.path / "config.enc", created.enc_handler) == created.config


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


def test_accept_unknown_host_key_survives_save_and_load(created: Project, host: Host) -> None:
    """True is saved and loaded back as True."""
    host.accept_unknown_host_key = True
    created.hosts = [host]
    created.save_hosts()
    created.load_hosts()
    assert created.hosts[0].accept_unknown_host_key is True


def test_hosts_saved_without_accept_unknown_host_key_load_as_false(created: Project) -> None:
    """A hosts.enc from before the field existed still loads, and trusts no unknown key."""
    write_encrypted(
        created.path / "hosts.enc",
        '[{"ip": "192.0.2.11", "ssh_username": "auditor", "ssh_password": "fake-login"}]',
        created.enc_handler,
    )
    created.load_hosts()
    assert created.hosts[0].accept_unknown_host_key is False


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
    (created.path / "hosts.enc").write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError, match="hosts.enc is damaged"):
        created.load_hosts()


def test_load_scans_restores_a_base_scan(created: Project) -> None:
    """A saved scan gets its time back."""
    scan = Scan()
    scan.write(created.path / "scans", created.enc_handler)
    created.load_scans()
    assert [loaded.performed_at for loaded in created.scans] == [scan.performed_at]


def test_load_scans_without_a_folder_gives_no_scans(tmp_path: Path, enc_handler: EncHandler) -> None:
    """A missing scans folder is not an error."""
    project = Project(tmp_path, ProjectConfig("office"), enc_handler)
    project.load_scans()
    assert project.scans == []


def test_load_restores_config_hosts_and_scans(created: Project, host: Host) -> None:
    """Loading brings back all parts of a project."""
    created.hosts = [host]
    created.save_hosts()
    scan = Scan()
    scan.write(created.path / "scans", created.enc_handler)

    loaded = Project.load(created.path, PROJECT_PASSWORD)
    assert loaded.config == created.config
    assert loaded.hosts == [host]
    assert [s.performed_at for s in loaded.scans] == [scan.performed_at]


def test_create_writes_the_salt_file(created: Project) -> None:
    """The salt file is what makes the key again on load, so a new project has one."""
    assert (created.path / SALT_FILE).is_file()
    assert EncHandler.load(created.path / SALT_FILE, PROJECT_PASSWORD).salt == created.enc_handler.salt


def test_create_does_not_keep_the_password(created: Project) -> None:
    """The project only has the key, and no file contains the password."""
    assert PROJECT_PASSWORD not in repr(created)
    for file in created.path.rglob("*"):
        if file.is_file():
            assert PROJECT_PASSWORD.encode("utf-8") not in file.read_bytes()


def test_two_projects_with_the_same_password_get_different_salts(created: Project, tmp_path: Path) -> None:
    """Each project has its own salt, so the same password gives another key."""
    other = Project.create(tmp_path / "school", ProjectConfig("school"), PROJECT_PASSWORD)
    assert other.enc_handler.salt != created.enc_handler.salt


def test_load_with_the_wrong_password_raises(created: Project) -> None:
    """A wrong password is noticed on config.enc, the first file decrypted, and is not called damage there."""
    with pytest.raises(ValueError, match="Wrong password") as error:
        Project.load(created.path, "wrong-fake-password")
    assert "config.enc is damaged" not in str(error.value)


def test_load_with_the_wrong_password_writes_nothing_to_the_log(created: Project) -> None:
    """A wrong key can't write entries that the right key could read."""
    with pytest.raises(ValueError):
        Project.load(created.path, "wrong-fake-password")
    created.log.load(created.enc_handler)
    assert [e.message for e in created.log.entries] == ["Project created"]


def test_load_without_a_salt_file_raises_file_not_found(created: Project) -> None:
    """Without the salt the key can't be made again."""
    (created.path / SALT_FILE).unlink()
    with pytest.raises(FileNotFoundError):
        Project.load(created.path, PROJECT_PASSWORD)


def test_create_with_an_empty_password_raises(tmp_path: Path) -> None:
    """A project can't be created without a password."""
    with pytest.raises(ValueError, match="Password"):
        Project.create(tmp_path / "bank", ProjectConfig("bank"), "")


def test_load_missing_project_raises(tmp_path: Path) -> None:
    """A folder that doesn't exist can't be loaded."""
    with pytest.raises(FileNotFoundError):
        Project.load(tmp_path / "missing", PROJECT_PASSWORD)


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
        Project.create(created.path, ProjectConfig("school"), PROJECT_PASSWORD)
    assert ProjectConfig.load(created.path / "config.enc", created.enc_handler).name == "bank"


def test_load_scans_restores_a_subclass(created: Project) -> None:
    """A scan loads as the class that wrote it."""
    FakeHostScan("192.0.2.11").write(created.path / "scans", created.enc_handler)
    created.load_scans()
    assert isinstance(created.scans[0], FakeHostScan)


def test_scan_file_cannot_call_other_functions(
    created: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The type in a scan file can only ever name a scan class."""
    calls = []
    monkeypatch.setattr(project_module, "helper", lambda **args: calls.append(args), raising=False)
    content = {"type": "helper", "performed_at": "2026-01-02T03:04:05"}
    write_encrypted(created.path / "scans" / "forged.scan.enc", json.dumps(content), created.enc_handler)
    with pytest.raises(ValueError):
        created.load_scans()
    assert calls == []


def test_load_scans_twice_does_not_duplicate(created: Project) -> None:
    """Loading replaces the list of scans."""
    Scan().write(created.path / "scans", created.enc_handler)
    created.load_scans()
    created.load_scans()
    assert len(created.scans) == 1


def test_loaded_scan_path_is_the_file_it_came_from(created: Project) -> None:
    """A scan file can't claim to be located somewhere else."""
    content = {"type": "Scan", "performed_at": "2026-01-02T03:04:05", "path": "somewhere/else"}
    file = created.path / "scans" / "forged.scan.enc"
    write_encrypted(file, json.dumps(content), created.enc_handler)
    created.load_scans()
    assert created.scans[0].path == file


def test_load_scans_returns_oldest_first(created: Project) -> None:
    """Scans are in the order they were performed."""
    older = FakeHostScan("192.0.2.11", performed_at=datetime(2025, 1, 1))
    newer = Scan(performed_at=datetime(2026, 1, 1))
    newer.write(created.path / "scans", created.enc_handler)
    older.write(created.path / "scans", created.enc_handler)
    created.load_scans()
    assert created.scans == [older, newer]


def test_load_scans_ignores_other_json_files(created: Project) -> None:
    """Only *.scan.enc files are scans."""
    write_encrypted(created.path / "scans" / "notes.json", "{}", created.enc_handler)
    created.load_scans()
    assert created.scans == []


@pytest.mark.parametrize("content", ["{}", '""', "5", "null"])
def test_load_hosts_rejects_json_that_is_not_a_list(created: Project, content: str) -> None:
    """Valid JSON of the wrong shape is an error."""
    write_encrypted(created.path / "hosts.enc", content, created.enc_handler)
    with pytest.raises(ValueError):
        created.load_hosts()


def test_failed_load_changes_nothing(created: Project, host: Host, tmp_path: Path) -> None:
    """If any part can't be loaded, the open project is left as it was."""
    broken = Project.create(tmp_path / "school", ProjectConfig("school"), PROJECT_PASSWORD)
    (broken.path / "hosts.enc").write_text("broken", encoding="utf-8")
    created.hosts = [host]
    with pytest.raises(ValueError):
        created = Project.load(broken.path, PROJECT_PASSWORD)
    assert created.path == tmp_path / "bank"
    assert created.config.name == "bank"
    assert created.hosts == [host]


def test_new_project_has_a_log_but_no_file(tmp_path: Path, enc_handler: EncHandler) -> None:
    """Making a Project object attaches its log without touching the disk."""
    project = Project(tmp_path, ProjectConfig("office"), enc_handler)
    assert project.log.path == tmp_path / "logs" / "project.log"
    assert project.log.entries == []
    assert not project.log.path.exists()


def test_create_logs_that_the_project_was_created(created: Project) -> None:
    """The first entry of a new project is its creation, in memory and in the file."""
    assert [e.message for e in created.log.entries] == ["Project created"]
    fresh = ProjectLog(created.log.path)
    fresh.load(created.enc_handler)
    assert fresh.entries == created.log.entries


def test_load_reads_the_log_and_logs_the_load(created: Project) -> None:
    """Loading brings back earlier entries and adds one for this load."""
    loaded = Project.load(created.path, PROJECT_PASSWORD)
    assert [e.message for e in loaded.log.entries] == ["Project created", "Project loaded"]


def test_failed_load_does_not_write_to_the_log(created: Project) -> None:
    """A project that can't be loaded isn't logged as loaded."""
    (created.path / "hosts.enc").write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        Project.load(created.path, PROJECT_PASSWORD)
    created.log.load(created.enc_handler)
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
    loaded = Project.load(created.path, PROJECT_PASSWORD)
    assert (created.path / "logs").is_dir()
    assert [e.message for e in loaded.log.entries] == [
        "Folder logs/ was missing and was created",
        "Project loaded",
    ]
    assert loaded.log.entries[0].level == LogLevel.WARNING


def test_load_warns_about_other_missing_folders_without_creating_them(created: Project) -> None:
    """Folders other than logs are only reported. Creating them is the user's choice."""
    (created.path / "scans").rmdir()
    loaded = Project.load(created.path, PROJECT_PASSWORD)
    assert not (created.path / "scans").exists()
    assert loaded.log.entries[-2].message == "Folder scans/ is missing"
    assert loaded.log.entries[-2].level == LogLevel.WARNING


def test_load_of_a_folder_that_is_not_a_project_creates_nothing(tmp_path: Path) -> None:
    """Without config.enc, load fails before it creates any folder."""
    with pytest.raises(FileNotFoundError):
        Project.load(tmp_path, PROJECT_PASSWORD)
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
    assert Project.load(created.path, PROJECT_PASSWORD).issues == {}


def test_load_reports_missing_folders_as_an_issue(created: Project) -> None:
    """The menu can see which folders are missing without reading the log."""
    (created.path / "configs").rmdir()
    (created.path / "scans").rmdir()
    loaded = Project.load(created.path, PROJECT_PASSWORD)
    assert loaded.issues == {ProjectIssue.MISSING_FOLDER: ["configs", "scans"]}


def test_recreated_logs_folder_is_not_an_issue(created: Project) -> None:
    """Load fixes a missing logs folder itself, so nothing is left to decide."""
    for file in (created.path / "logs").iterdir():
        file.unlink()
    (created.path / "logs").rmdir()
    assert Project.load(created.path, PROJECT_PASSWORD).issues == {}


def test_create_missing_folders_clears_the_issue(created: Project) -> None:
    """Once the folders exist, the issue is gone."""
    (created.path / "scans").rmdir()
    loaded = Project.load(created.path, PROJECT_PASSWORD)
    loaded.create_missing_folders()
    assert loaded.issues == {}


@pytest.mark.parametrize("name", ["office", "Västerås lab", "a" * 64])
def test_valid_project_name_is_accepted(name: str) -> None:
    """Any printable name up to 64 characters is fine, also with spaces and non-ASCII letters."""
    assert ProjectConfig(name).name == name


@pytest.mark.parametrize("name", ["", "   ", "office\nreload", "a" * 65, None, 5])
def test_invalid_project_name_raises(name: object) -> None:
    """A project name is printable text, not empty and not too long."""
    with pytest.raises(ValueError):
        ProjectConfig(name)  # type: ignore[arg-type]


@pytest.mark.parametrize("port", [1, 22, 65535])
def test_valid_ssh_port_is_accepted(port: int) -> None:
    """Every TCP port number can be used for SSH."""
    assert ProjectConfig("office", ssh_port=port).ssh_port == port


@pytest.mark.parametrize("port", [0, 65536, -22, 22.0, True, "22", None])
def test_invalid_ssh_port_raises(port: object) -> None:
    """A port is a whole number from 1 to 65535."""
    with pytest.raises(ValueError):
        ProjectConfig("office", ssh_port=port)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", [0, 301, 1.5, True, "10", None])
def test_invalid_ssh_timeout_raises(timeout: object) -> None:
    """A timeout is a whole number of seconds from 1 to 300."""
    with pytest.raises(ValueError):
        ProjectConfig("office", ssh_timeout=timeout)  # type: ignore[arg-type]


@pytest.mark.parametrize("created", ["yesterday", "2026-01-02", "2026-13-01 00:00:00", None])
def test_invalid_created_time_raises(created: object) -> None:
    """The created time must be in the format current_timestamp writes."""
    with pytest.raises(ValueError):
        ProjectConfig("office", created_time=created)  # type: ignore[arg-type]


def test_loading_a_config_with_a_bad_value_raises(tmp_path: Path, enc_handler: EncHandler) -> None:
    """A hand-edited config.enc is checked when it's loaded."""
    path = tmp_path / "config.enc"
    ProjectConfig("office").save(path, enc_handler)
    data = json.loads(read_decrypted(path, enc_handler))
    data["ssh_port"] = 99999
    write_encrypted(path, json.dumps(data), enc_handler)
    with pytest.raises(ValueError):
        ProjectConfig.load(path, enc_handler)


def test_add_host_saves_and_logs_it(created: Project, host: Host) -> None:
    """An added host is in memory, in hosts.enc, and in the log."""
    created.add_host(host)
    assert created.hosts == [host]
    assert Project.load(created.path, PROJECT_PASSWORD).hosts == [host]
    assert created.log.entries[-1].message == "Added host 192.0.2.11"


def test_add_host_with_an_existing_ip_raises(created: Project, host: Host) -> None:
    """Two hosts can't share an IP, and the first one is kept."""
    created.add_host(host)
    other = Host("192.0.2.11", "other", "fake-other")
    with pytest.raises(ValueError):
        created.add_host(other)
    assert created.hosts == [host]


def test_add_host_that_cant_be_saved_is_taken_out(tmp_path: Path, host: Host, enc_handler: EncHandler) -> None:
    """If hosts.enc can't be written, the host isn't kept in memory either."""
    project = Project(tmp_path / "missing", ProjectConfig("office"), enc_handler)
    with pytest.raises(OSError):
        project.add_host(host)
    assert project.hosts == []


def test_remove_host_saves_logs_and_returns_it(created: Project, host: Host) -> None:
    """A removed host is gone from memory and from hosts.enc, and is returned."""
    second = Host("192.0.2.12", "auditor", "fake-login")
    created.add_host(host)
    created.add_host(second)
    assert created.remove_host("192.0.2.11") == host
    assert created.hosts == [second]
    assert Project.load(created.path, PROJECT_PASSWORD).hosts == [second]
    assert created.log.entries[-1].message == "Removed host 192.0.2.11"


def test_remove_unknown_host_raises(created: Project, host: Host) -> None:
    """Removing an IP that isn't there is an error, and nothing changes."""
    created.add_host(host)
    with pytest.raises(ValueError):
        created.remove_host("192.0.2.99")
    assert created.hosts == [host]


def test_remove_host_that_cant_be_saved_is_put_back(created: Project, host: Host) -> None:
    """If hosts.enc can't be written, the host stays, in the same place."""
    second = Host("192.0.2.12", "auditor", "fake-login")
    created.add_host(host)
    created.add_host(second)
    created.path = created.path / "missing"  # saving now fails
    with pytest.raises(OSError):
        created.remove_host("192.0.2.11")
    assert created.hosts == [host, second]


def test_load_hosts_with_duplicate_ips_raises(created: Project, host: Host) -> None:
    """A hosts.enc edited to have the same IP twice doesn't load."""
    created.hosts = [host, Host("192.0.2.11", "other", "fake-other")]
    created.save_hosts()
    with pytest.raises(ValueError):
        created.load_hosts()


@pytest.mark.parametrize(
    "content",
    ["not json", "[1, 2]", '{"name": "office", "colour": "red"}', '{"ssh_port": 22}', '{"name": "office", "ssh_port": 0}'],
)
def test_damaged_config_names_the_file(tmp_path: Path, content: str, enc_handler: EncHandler) -> None:
    """Every kind of damage in config.enc is a ValueError that says which file it is."""
    path = tmp_path / "config.enc"
    write_encrypted(path, content, enc_handler)
    with pytest.raises(ValueError, match="config.enc is damaged"):
        ProjectConfig.load(path, enc_handler)


def test_missing_config_is_still_file_not_found(tmp_path: Path, enc_handler: EncHandler) -> None:
    """A missing file isn't damage: it stays a FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        ProjectConfig.load(tmp_path / "config.enc", enc_handler)


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"ip": "192.0.2.11"}',  # not a list
        '["192.0.2.11"]',  # a list, but not of hosts
        '[{"ip": "192.0.2.11", "ssh_username": "a", "ssh_password": "b", "colour": "red"}]',  # unknown field
        '[{"ip": "192.0.2.11", "ssh_username": "a"}]',  # missing field
        '[{"ip": "999.0.2.11", "ssh_username": "a", "ssh_password": "b"}]',  # invalid value
    ],
)
def test_damaged_hosts_name_the_file_and_change_nothing(created: Project, host: Host, content: str) -> None:
    """Every kind of damage in hosts.enc is a ValueError naming the file, and the hosts in memory stay."""
    created.hosts = [host]
    write_encrypted(created.path / "hosts.enc", content, created.enc_handler)
    with pytest.raises(ValueError, match="hosts.enc is damaged"):
        created.load_hosts()
    assert created.hosts == [host]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",  # not a scan
        '{"performed_at": "2026-01-02T03:04:05"}',  # no type
        '{"type": "Scan"}',  # no time
        '{"type": "Scan", "performed_at": "yesterday"}',  # bad time
        '{"type": "Scan", "performed_at": "2026-01-02T03:04:05", "colour": "red"}',  # unknown field
        '{"type": "Nope", "performed_at": "2026-01-02T03:04:05"}',  # unknown type
    ],
)
def test_damaged_scan_names_the_file(created: Project, content: str) -> None:
    """Every kind of damage in a scan file is a ValueError that says which file it is."""
    write_encrypted(created.path / "scans" / "bad.scan.enc", content, created.enc_handler)
    with pytest.raises(ValueError, match="bad.scan.enc is damaged"):
        created.load_scans()


def test_hosts_file_that_cant_be_decrypted_names_the_file(created: Project) -> None:
    """Once config.enc was decrypted the password is right, so a hosts.enc that fails is damaged."""
    (created.path / "hosts.enc").write_text("not a token", encoding="utf-8")
    with pytest.raises(ValueError, match="hosts.enc is damaged: Wrong password, or the file is damaged"):
        created.load_hosts()


def test_load_of_damaged_project_names_the_file(created: Project) -> None:
    """Project.load passes the clear error on."""
    (created.path / "hosts.enc").write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError, match="hosts.enc is damaged"):
        Project.load(created.path, PROJECT_PASSWORD)
