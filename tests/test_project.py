"""Tests for netaudit/project.py."""

import time
from pathlib import Path

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
