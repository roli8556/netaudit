"""Tests for netaudit/project.py."""

import json
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from netaudit.host import Host
from netaudit.project import Project, ProjectConfig


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
