"""Tests for netaudit/menu.py."""

from pathlib import Path

import pytest

from netaudit.menu import Menu, is_safe_folder_name
from netaudit.host import Host
from netaudit.project import Project, ProjectConfig


def fake_input(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    """Make input() return these answers one by one, as if the user typed them."""
    remaining = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(remaining))


def test_choosing_exit_ends_the_menu(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Exit stops run and says goodbye."""
    fake_input(monkeypatch, ["q"])
    Menu().run()
    out = capsys.readouterr().out
    assert "1. Create project" in out
    assert out.endswith("Bye\n")


@pytest.mark.parametrize("bad", ["3", "9", "0", "abc", "quit", "1.0", "²"])
def test_invalid_choice_shows_the_menu_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    """Anything but a listed number is refused on stderr, and the start menu is shown again."""
    fake_input(monkeypatch, [bad, "q"])
    Menu().run()
    captured = capsys.readouterr()
    assert "Please type 1, 2 or q." in captured.err
    assert captured.out.count("Start menu") == 2


def test_choice_may_have_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spaces around the number don't matter."""
    fake_input(monkeypatch, [" q "])
    assert Menu().start_menu() is False


@pytest.mark.parametrize("choice, action", [("1", "create_project_menu"), ("2", "load_project_menu")])
def test_choice_calls_its_action(monkeypatch: pytest.MonkeyPatch, choice: str, action: str) -> None:
    """Each start menu choice calls its own method, and the menu continues afterwards."""
    called = []
    monkeypatch.setattr(Menu, action, lambda self: called.append(action))
    fake_input(monkeypatch, [choice])
    assert Menu().start_menu() is True
    assert called == [action]


def test_ask_strips_spaces_and_asks_again_when_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty or blank answer is refused, a real one comes back without spaces."""
    fake_input(monkeypatch, ["", "   ", "  office  "])
    assert Menu().ask("Name: ") == "office"
    assert capsys.readouterr().err.count("Please type a value.") == 2


def test_error_from_an_action_is_shown_and_the_menu_continues(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ValueError from an action is printed to stderr, not raised, and the menu runs on."""
    calls = iter([ValueError("bad value"), False])

    def fake_start_menu(self: Menu) -> bool:
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(Menu, "start_menu", fake_start_menu)
    Menu().run()
    captured = capsys.readouterr()
    assert "Error: bad value" in captured.err
    assert captured.out.endswith("Bye\n")


def test_new_menu_has_no_project() -> None:
    """The start menu begins without an open project."""
    assert Menu().project is None


def test_capital_q_also_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit works with Q as well as q."""
    fake_input(monkeypatch, ["Q"])
    assert Menu().start_menu() is False


def test_create_project_with_defaults(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Name, location and Enter twice create the project with default settings, then q closes it."""
    fake_input(monkeypatch, ["office", str(tmp_path), "", "", "q"])
    menu = Menu()
    menu.create_project_menu()
    config = Project.load(tmp_path / "office").config
    assert (config.name, config.ssh_port, config.ssh_timeout) == ("office", 22, 10)
    out = capsys.readouterr().out
    assert "WARNING: this project is not encrypted yet" in out
    assert "Project: office (0 hosts)" in out
    assert menu.project is None  # closed


def test_create_project_with_own_port_and_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Typed numbers replace the defaults."""
    fake_input(monkeypatch, ["lab", str(tmp_path), "2222", "30", "q"])
    Menu().create_project_menu()
    config = Project.load(tmp_path / "lab").config
    assert (config.ssh_port, config.ssh_timeout) == (2222, 30)


def test_create_project_from_the_start_menu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Closing the new project returns to the start menu."""
    fake_input(monkeypatch, ["1", "office", str(tmp_path), "", "", "q", "q"])
    Menu().run()
    out = capsys.readouterr().out
    assert out.count("Start menu") == 2
    assert out.endswith("Bye\n")


@pytest.mark.parametrize("name", ["../evil", "a:b", "CON", "nul", "a/b", "a\b", "a.b", "what?", "x" * 65])
def test_create_project_with_unsafe_name_creates_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    """A name that isn't a safe folder name is refused before anything is asked or created."""
    fake_input(monkeypatch, [name])
    with pytest.raises(ValueError):
        Menu().create_project_menu()
    assert list(tmp_path.iterdir()) == []


def test_create_project_in_missing_location_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The location must already exist, so a typo doesn't create folders somewhere unexpected."""
    fake_input(monkeypatch, ["office", str(tmp_path / "missing")])
    with pytest.raises(ValueError):
        Menu().create_project_menu()
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("port", ["abc", "70000", "0", "-22", "2.5"])
def test_create_project_with_bad_port_creates_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, port: str
) -> None:
    """A port that isn't a whole number from 1 to 65535 is refused, and no folder is made."""
    fake_input(monkeypatch, ["office", str(tmp_path), port, ""])
    with pytest.raises(ValueError):
        Menu().create_project_menu()
    assert list(tmp_path.iterdir()) == []


def test_create_project_over_an_existing_one_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An existing project folder is never overwritten."""
    Project.create(tmp_path / "office", ProjectConfig("office", ssh_port=2222))
    fake_input(monkeypatch, ["office", str(tmp_path), "", ""])
    with pytest.raises(FileExistsError):
        Menu().create_project_menu()
    assert Project.load(tmp_path / "office").config.ssh_port == 2222


def test_create_error_is_shown_and_start_menu_continues(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bad answer while creating shows an error on stderr, then the start menu again."""
    fake_input(monkeypatch, ["1", "../evil", "q"])
    Menu().run()
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert captured.out.count("Start menu") == 2


def test_project_menu_refuses_other_choices(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Only the listed choices work in the project menu."""
    menu = Menu()
    menu.project = Project.create(tmp_path / "office", ProjectConfig("office"))
    fake_input(monkeypatch, ["2", "q"])
    menu.project_menu()
    assert "Please type 1 or q." in capsys.readouterr().err
    assert menu.project is None


@pytest.mark.parametrize("answer, expected", [("", 22), ("  ", 22), ("2222", 2222), (" 15 ", 15)])
def test_ask_number_gives_default_or_number(monkeypatch: pytest.MonkeyPatch, answer: str, expected: int) -> None:
    """Enter gives the default, a whole number gives that number."""
    fake_input(monkeypatch, [answer])
    assert Menu().ask_number("Port: ", 22) == expected


@pytest.mark.parametrize("answer", ["abc", "-1", "1.5", "²", "1e3"])
def test_ask_number_refuses_anything_else(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    """Only plain digits are a number."""
    fake_input(monkeypatch, [answer])
    with pytest.raises(ValueError):
        Menu().ask_number("Port: ", 22)


@pytest.mark.parametrize("name", ["office", "Västerås lab", "lab_2", "core-net", "x" * 64])
def test_safe_folder_names(name: str) -> None:
    """Letters (also non-English), digits, spaces, - and _ are fine."""
    assert is_safe_folder_name(name)


@pytest.mark.parametrize("name", ["", " office", "office ", "..", "a.b", "C:", "a/b", "COM1", "lpt9", "x" * 65])
def test_unsafe_folder_names(name: str) -> None:
    """Path parts, dots, colons, reserved Windows names and edge spaces are refused."""
    assert not is_safe_folder_name(name)


@pytest.fixture
def saved(tmp_path: Path) -> Project:
    """A project on disk with one host, ready to be loaded."""
    project = Project.create(tmp_path / "office", ProjectConfig("office"))
    project.add_host(Host("192.0.2.11", "auditor", "fake-login"))
    return project


def test_load_project_and_close_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """Loading shows the project and its hosts, then q closes it."""
    fake_input(monkeypatch, [str(saved.path), "q"])
    menu = Menu()
    menu.load_project_menu()
    out = capsys.readouterr().out
    assert "Loaded project 'office' (1 hosts)" in out
    assert "WARNING: this project is not encrypted yet" in out
    assert "Project: office (1 hosts)" in out
    assert menu.project is None


def test_load_project_from_the_start_menu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """Closing the loaded project returns to the start menu."""
    fake_input(monkeypatch, ["2", str(saved.path), "q", "q"])
    Menu().run()
    out = capsys.readouterr().out
    assert out.count("Start menu") == 2
    assert out.endswith("Bye\n")


def test_show_hosts_without_hosts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """An empty project says so instead of printing an empty table."""
    menu = Menu()
    menu.project = Project.create(tmp_path / "office", ProjectConfig("office"))
    menu.show_hosts()
    out = capsys.readouterr().out
    assert "No hosts yet." in out
    assert "IP" not in out


def test_show_hosts_never_shows_passwords(capsys: pytest.CaptureFixture[str], saved: Project) -> None:
    """Each host is a row with - for what isn't read yet, and no password appears anywhere."""
    saved.add_host(Host("192.0.2.12", "admin", "fake-login-2", hostname="SW2", enable_password="fake-enable",
                        privilege_level=15, accept_unknown_host_key=True))
    menu = Menu()
    menu.project = saved
    menu.show_hosts()
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert lines[1].split() == ["IP", "Username", "Hostname", "Privilege", "Enable", "password", "Accept", "unknown", "key"]
    assert lines[2].split() == ["192.0.2.11", "auditor", "-", "-", "not", "set", "no"]
    assert lines[3].split() == ["192.0.2.12", "admin", "SW2", "15", "set", "yes"]
    for password in ["fake-login", "fake-enable"]:  # fake-login is also part of fake-login-2
        assert password not in captured.out + captured.err


def test_project_menu_shows_hosts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """Choice 1 shows the hosts, then the project menu comes back."""
    fake_input(monkeypatch, [str(saved.path), "1", "q"])
    Menu().load_project_menu()
    out = capsys.readouterr().out
    assert "192.0.2.11" in out
    assert out.count("Project: office") == 2


def test_load_missing_folder_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A path that isn't a folder is refused with a clear message."""
    fake_input(monkeypatch, [str(tmp_path / "missing")])
    with pytest.raises(ValueError, match="is not a folder"):
        Menu().load_project_menu()


def test_load_folder_that_is_not_a_project_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A folder without config.json isn't a project, and nothing is created in it."""
    fake_input(monkeypatch, [str(tmp_path)])
    with pytest.raises(ValueError, match="is not a netaudit project"):
        Menu().load_project_menu()
    assert list(tmp_path.iterdir()) == []


def test_load_damaged_project_shows_the_file_and_returns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """A damaged hosts.json shows an error naming the file, then the start menu, with no project open."""
    (saved.path / "hosts.json").write_text("broken", encoding="utf-8")
    fake_input(monkeypatch, ["2", str(saved.path), "q"])
    menu = Menu()
    menu.run()
    captured = capsys.readouterr()
    assert "hosts.json is damaged" in captured.err
    assert captured.out.count("Start menu") == 2
    assert menu.project is None


def test_missing_folders_can_be_created(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """Choice 1 creates the missing folders, then the project menu opens."""
    (saved.path / "scans").rmdir()
    fake_input(monkeypatch, [str(saved.path), "1", "q"])
    Menu().load_project_menu()
    out = capsys.readouterr().out
    assert "These project folders are missing: scans" in out
    assert "Project: office" in out
    assert (saved.path / "scans").is_dir()


def test_missing_folders_can_be_left_missing(monkeypatch: pytest.MonkeyPatch, saved: Project) -> None:
    """Choice 2 opens the project without creating anything."""
    (saved.path / "scans").rmdir()
    (saved.path / "configs").rmdir()
    fake_input(monkeypatch, [str(saved.path), "2", "q"])
    Menu().load_project_menu()
    assert not (saved.path / "scans").exists()
    assert not (saved.path / "configs").exists()


def test_missing_folders_q_closes_the_project(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """q in the missing-folders question closes the project without opening the project menu."""
    (saved.path / "scans").rmdir()
    fake_input(monkeypatch, [str(saved.path), "x", "q"])
    menu = Menu()
    menu.load_project_menu()
    captured = capsys.readouterr()
    assert "Please type 1, 2 or q." in captured.err
    assert "Project: office" not in captured.out
    assert menu.project is None
