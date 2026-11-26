"""Tests for netaudit/menu.py."""

import pytest

from netaudit.menu import Menu


def fake_input(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    """Make input() return these answers one by one, as if the user typed them."""
    remaining = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(remaining))


def test_choosing_exit_ends_the_menu(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Exit stops run and says goodbye."""
    fake_input(monkeypatch, ["3"])
    Menu().run()
    out = capsys.readouterr().out
    assert "1. Create project" in out
    assert out.endswith("Bye\n")


@pytest.mark.parametrize("bad", ["9", "0", "abc", "1.0", "²"])
def test_invalid_choice_shows_the_menu_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    """Anything but a listed number is refused on stderr, and the start menu is shown again."""
    fake_input(monkeypatch, [bad, "3"])
    Menu().run()
    captured = capsys.readouterr()
    assert "Please type a number from 1 to 3." in captured.err
    assert captured.out.count("Start menu") == 2


def test_choice_may_have_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spaces around the number don't matter."""
    fake_input(monkeypatch, [" 3 "])
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
    """Create and load aren't built yet, so the menu is shown again."""
    fake_input(monkeypatch, ["1", "3"])
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
