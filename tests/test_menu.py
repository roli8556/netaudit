"""Tests for netaudit/menu.py."""

from pathlib import Path

import pytest

from netaudit.menu import Menu, is_safe_folder_name, make_printable
from netaudit.host import Host
from netaudit.log import LogCategory, LogEntry, LogLevel
from netaudit.project import Project, ProjectConfig


def fake_input(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    """Make input() return these answers one by one, as if the user typed them."""
    remaining = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(remaining))


def fake_getpass(monkeypatch: pytest.MonkeyPatch, passwords: list[str]) -> None:
    """Make the menu's getpass() return these passwords one by one, as if the user typed them."""
    remaining = iter(passwords)
    monkeypatch.setattr("netaudit.menu.getpass", lambda prompt="": next(remaining))


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
    fake_input(monkeypatch, ["5", "q"])
    menu.project_menu()
    assert "Please type 1, 2, 3, 4 or q." in capsys.readouterr().err
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
    assert lines[1].split() == ["#", "IP", "Username", "Hostname", "Privilege", "Enable", "password", "Accept", "unknown",
                                "key"]
    assert lines[2].split() == ["1", "192.0.2.11", "auditor", "-", "-", "not", "set", "no"]
    assert lines[3].split() == ["2", "192.0.2.12", "admin", "SW2", "15", "set", "yes"]
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


@pytest.mark.parametrize("answer, accept", [("", False), ("n", False), ("N", False), ("y", True), (" Y ", True)])
def test_add_host_saves_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project, answer: str, accept: bool
) -> None:
    """The new host is added and saved, Enter means no, and the password is never printed."""
    fake_input(monkeypatch, ["192.0.2.20", "admin", answer])
    fake_getpass(monkeypatch, ["fake-new-login", ""])
    menu = Menu()
    menu.project = saved
    menu.add_host_menu()
    captured = capsys.readouterr()
    assert "Added host 192.0.2.20" in captured.out
    assert "fake-new-login" not in captured.out + captured.err
    reloaded = Project.load(saved.path)
    assert reloaded.hosts[-1] == Host("192.0.2.20", "admin", "fake-new-login", accept_unknown_host_key=accept)


@pytest.mark.parametrize(
    "answers, password, message",
    [
        (["192.0.2.999", "admin", ""], "fake-new-login", "Invalid IPv4 address"),
        (["192.0.2.11", "admin", ""], "fake-new-login", "already exists"),  # the IP of the saved host
        (["192.0.2.20", "admin", ""], "", "SSH password cannot be empty"),
        (["192.0.2.20", "admin", "yes"], "fake-new-login", "is not y or n"),
    ],
)
def test_add_host_with_a_bad_answer_adds_nothing(
    monkeypatch: pytest.MonkeyPatch, saved: Project, answers: list[str], password: str, message: str
) -> None:
    """A bad answer raises a clear ValueError, and the project and hosts.json keep only the saved host."""
    fake_input(monkeypatch, answers)
    fake_getpass(monkeypatch, [password, ""])
    menu = Menu()
    menu.project = saved
    with pytest.raises(ValueError, match=message):
        menu.add_host_menu()
    assert len(saved.hosts) == 1
    assert len(Project.load(saved.path).hosts) == 1


def test_add_host_with_an_enable_password_saves_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """A typed enable password is stored with the host and never printed."""
    fake_input(monkeypatch, ["192.0.2.20", "admin", ""])
    fake_getpass(monkeypatch, ["fake-new-login", "fake-new-enable"])
    menu = Menu()
    menu.project = saved
    menu.add_host_menu()
    captured = capsys.readouterr()
    assert "fake-new-enable" not in captured.out + captured.err
    reloaded = Project.load(saved.path)
    assert reloaded.hosts[-1] == Host("192.0.2.20", "admin", "fake-new-login", enable_password="fake-new-enable")


def test_add_host_without_an_enable_password_stores_none(
    monkeypatch: pytest.MonkeyPatch, saved: Project
) -> None:
    """Enter at the enable password means the host has none: None, not an empty string."""
    fake_input(monkeypatch, ["192.0.2.20", "admin", ""])
    fake_getpass(monkeypatch, ["fake-new-login", ""])
    menu = Menu()
    menu.project = saved
    menu.add_host_menu()
    assert Project.load(saved.path).hosts[-1].enable_password is None


def test_add_host_with_a_line_break_in_the_enable_password_adds_nothing(
    monkeypatch: pytest.MonkeyPatch, saved: Project
) -> None:
    """A control character in the enable password is refused, and the message doesn't show the password."""
    fake_input(monkeypatch, ["192.0.2.20", "admin", ""])
    fake_getpass(monkeypatch, ["fake-new-login", "fake-enable\nreload"])
    menu = Menu()
    menu.project = saved
    with pytest.raises(ValueError, match="Enable password contains a control character") as error:
        menu.add_host_menu()
    assert "fake-enable" not in str(error.value)
    assert len(Project.load(saved.path).hosts) == 1


def test_error_in_project_menu_keeps_the_project_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """A bad IP shows an error and the project menu again, without showing the password."""
    fake_input(monkeypatch, ["2", "999.0.0.1", "admin", "", "q"])
    fake_getpass(monkeypatch, ["fake-new-login", ""])
    menu = Menu()
    menu.project = saved
    menu.project_menu()
    captured = capsys.readouterr()
    assert "Error: Invalid IPv4 address" in captured.err
    assert "fake-new-login" not in captured.out + captured.err
    assert captured.out.count("Project: office") == 2


@pytest.fixture
def two_hosts(saved: Project) -> Menu:
    """A menu with the saved project open, now with two hosts: 1 is 192.0.2.11, 2 is 192.0.2.12."""
    saved.add_host(Host("192.0.2.12", "admin", "fake-login-2"))
    menu = Menu()
    menu.project = saved
    return menu


def test_remove_host_by_number(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], two_hosts: Menu
) -> None:
    """Number 2 removes the second host in the list, after y, and hosts.json no longer has it."""
    fake_input(monkeypatch, ["2", "y"])
    two_hosts.remove_host_menu()
    assert "Removed host 192.0.2.12" in capsys.readouterr().out
    assert [host.ip for host in two_hosts.project.hosts] == ["192.0.2.11"]
    assert [host.ip for host in Project.load(two_hosts.project.path).hosts] == ["192.0.2.11"]


@pytest.mark.parametrize("confirm", ["", "n", "N"])
def test_remove_host_keeps_it_unless_confirmed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], two_hosts: Menu, confirm: str
) -> None:
    """Enter or n at the confirmation removes nothing."""
    fake_input(monkeypatch, ["1", confirm])
    two_hosts.remove_host_menu()
    assert "Nothing removed." in capsys.readouterr().out
    assert len(Project.load(two_hosts.project.path).hosts) == 2


def test_remove_host_q_goes_back(monkeypatch: pytest.MonkeyPatch, two_hosts: Menu) -> None:
    """q at the number question removes nothing and asks nothing more."""
    fake_input(monkeypatch, ["q"])
    two_hosts.remove_host_menu()
    assert len(two_hosts.project.hosts) == 2


@pytest.mark.parametrize("number", ["0", "3", "-1", "abc", "²", "1.0"])
def test_remove_host_with_a_bad_number_removes_nothing(
    monkeypatch: pytest.MonkeyPatch, two_hosts: Menu, number: str
) -> None:
    """Only a number shown in the list is accepted."""
    fake_input(monkeypatch, [number])
    with pytest.raises(ValueError, match="is not a host number from 1 to 2"):
        two_hosts.remove_host_menu()
    assert len(two_hosts.project.hosts) == 2


def test_remove_host_with_a_bad_confirmation_removes_nothing(monkeypatch: pytest.MonkeyPatch, two_hosts: Menu) -> None:
    """Anything but y, n or Enter at the confirmation is refused."""
    fake_input(monkeypatch, ["1", "yes"])
    with pytest.raises(ValueError, match="is not y or n"):
        two_hosts.remove_host_menu()
    assert len(two_hosts.project.hosts) == 2


def test_remove_host_without_hosts(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """An empty project says there is nothing to remove, without asking anything."""
    menu = Menu()
    menu.project = Project.create(tmp_path / "office", ProjectConfig("office"))
    menu.remove_host_menu()  # no fake_input: asking would fail the test
    assert "No hosts to remove." in capsys.readouterr().out


def test_project_menu_removes_hosts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], two_hosts: Menu
) -> None:
    """Choice 3 removes a host, then the project menu comes back with one host fewer."""
    fake_input(monkeypatch, ["3", "1", "y", "q"])
    two_hosts.project_menu()
    out = capsys.readouterr().out
    assert "Project: office (2 hosts)" in out
    assert "Project: office (1 hosts)" in out


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


@pytest.mark.parametrize("text", ["", "Added host 192.0.2.20", "Projekt 'kontor' öppnat", r"C:\Users"])
def test_make_printable_keeps_printable_text(text: str) -> None:
    """Printable text, also outside English and with backslashes, comes back unchanged."""
    assert make_printable(text) == text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("line 1\nline 2", r"line 1\nline 2"),
        ("a\tb", r"a\tb"),
        ("\x1b[31mred", r"\x1b[31mred"),
        ("end\r", r"end\r"),
    ],
)
def test_make_printable_escapes_control_characters(text: str, expected: str) -> None:
    """Control characters are shown as escape codes, so the result is one line without control codes."""
    assert make_printable(text) == expected


ROWS = ["row 1", "row 2", "row 3", "row 4", "row 5"]


def test_print_as_pages_on_one_page_asks_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rows that fit on one page are all printed. No fake_input: if it asked, the real input() would fail."""
    monkeypatch.setattr("netaudit.menu.PAGE_SIZE", 2)
    Menu().print_as_pages("HEADER", ROWS[:2])
    assert capsys.readouterr().out == "HEADER\nrow 1\nrow 2\n"


def test_print_as_pages_enter_shows_every_page(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Enter after each page shows all rows, with the header on every page and no question after the last."""
    monkeypatch.setattr("netaudit.menu.PAGE_SIZE", 2)
    fake_input(monkeypatch, ["", ""])
    Menu().print_as_pages("HEADER", ROWS)
    out = capsys.readouterr().out
    for row in ROWS:
        assert row in out
    assert out.count("HEADER") == 3


def test_print_as_pages_q_stops_early(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """q after the first page goes back without showing the rest."""
    monkeypatch.setattr("netaudit.menu.PAGE_SIZE", 2)
    fake_input(monkeypatch, ["Q"])
    Menu().print_as_pages("HEADER", ROWS)
    out = capsys.readouterr().out
    assert "row 2" in out
    assert "row 3" not in out


def test_print_as_pages_bad_answer_asks_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Another answer shows an error and asks again on the same page."""
    monkeypatch.setattr("netaudit.menu.PAGE_SIZE", 2)
    fake_input(monkeypatch, ["x", "q"])
    Menu().print_as_pages("HEADER", ROWS)
    captured = capsys.readouterr()
    assert "Please press Enter or type q." in captured.err
    assert captured.out.count("HEADER") == 1
    assert "row 3" not in captured.out


def test_print_as_pages_without_rows_prints_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    """An empty list prints nothing, not even the header."""
    Menu().print_as_pages("HEADER", [])
    assert capsys.readouterr().out == ""


def test_show_log_when_empty(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """A project with nothing logged says so. Project() itself doesn't touch the disk or log anything."""
    menu = Menu()
    menu.project = Project(tmp_path / "office", ProjectConfig("office"))
    menu.show_log()
    assert "The log is empty." in capsys.readouterr().out


def test_show_log_in_file_order(capsys: pytest.CaptureFixture[str], saved: Project) -> None:
    """The entries are shown oldest first, with their number, level and category."""
    menu = Menu()
    menu.project = saved
    menu.show_log()
    out = capsys.readouterr().out
    created = out.index("Project created")
    added = out.index("Added host 192.0.2.11")
    assert created < added
    assert "INFO      HOST      Added host 192.0.2.11" in out


def test_show_log_entry_without_number(capsys: pytest.CaptureFixture[str], saved: Project) -> None:
    """An entry that isn't in the file (a warning about a damaged line) shows - as its number."""
    saved.log.entries.append(LogEntry("Skipped damaged line 3", LogCategory.MISC, LogLevel.WARNING))
    menu = Menu()
    menu.project = saved
    menu.show_log()
    rows = capsys.readouterr().out.splitlines()
    assert rows[-1].startswith("-     ")
    assert rows[-1].endswith("WARNING   MISC      Skipped damaged line 3")


def test_show_log_keeps_a_message_on_one_row(capsys: pytest.CaptureFixture[str], saved: Project) -> None:
    """A line break in a message is shown as \\n, so it can't fake an extra row."""
    saved.log.entries.append(LogEntry("fake\n7     2026-01-01 00:00:00  INFO      CHECK     All passed", LogCategory.HOST))
    menu = Menu()
    menu.project = saved
    menu.show_log()
    rows = capsys.readouterr().out.splitlines()
    assert rows[-1].endswith(r"fake\n7     2026-01-01 00:00:00  INFO      CHECK     All passed")
    assert not any(row.startswith("7     ") for row in rows)


def test_show_log_from_project_menu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], saved: Project
) -> None:
    """Choice 4 shows the log, then the project menu comes back."""
    fake_input(monkeypatch, ["4", "q"])
    menu = Menu()
    menu.project = saved
    menu.project_menu()
    out = capsys.readouterr().out
    assert "Project created" in out
    assert out.count("Project: office") == 2
