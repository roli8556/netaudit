"""Tests for netaudit/menu.py."""

from pathlib import Path

import pytest

from netaudit.menu import Menu, is_safe_folder_name
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


def test_not_yet_available_choice_returns_to_the_menu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Load isn't built yet, so the menu is shown again."""
    fake_input(monkeypatch, ["2", "q"])
    Menu().run()
    assert "Not available yet." in capsys.readouterr().out


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
    """Only q works in the project menu for now."""
    menu = Menu()
    menu.project = Project.create(tmp_path / "office", ProjectConfig("office"))
    fake_input(monkeypatch, ["1", "q"])
    menu.project_menu()
    assert "Please type q." in capsys.readouterr().err
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
