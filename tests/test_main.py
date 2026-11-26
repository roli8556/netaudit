"""Tests for main.py."""

import pytest

from main import main


def test_main_runs_the_menu(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """main starts the menu, and Exit ends it."""
    monkeypatch.setattr("builtins.input", lambda prompt="": "q")
    main()
    out = capsys.readouterr().out
    assert out.startswith("netaudit")
    assert out.endswith("Bye\n")


@pytest.mark.parametrize("stop", [KeyboardInterrupt, EOFError])
def test_main_ends_cleanly_on_ctrl_c_or_end_of_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stop: type[BaseException]
) -> None:
    """Ctrl+C or end of input says goodbye instead of showing a traceback."""

    def interrupted(prompt: str = "") -> str:
        raise stop

    monkeypatch.setattr("builtins.input", interrupted)
    main()
    assert capsys.readouterr().out.endswith("Bye\n")
