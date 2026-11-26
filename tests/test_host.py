"""Tests for netaudit/host.py."""

import pytest

from netaudit.host import Host, is_valid_hostname


def test_host_stores_its_fields() -> None:
    """A host keeps everything it was given."""
    host = Host("192.0.2.11", "auditor", "fake-login", hostname="core", enable_password="fake-enable", privilege_level=15)
    assert host.ip == "192.0.2.11"
    assert host.hostname == "core"
    assert host.ssh_username == "auditor"
    assert host.ssh_password == "fake-login"
    assert host.enable_password == "fake-enable"
    assert host.privilege_level == 15


def test_privilege_level_starts_as_not_read() -> None:
    """The level is read from the device after connecting, so a new host has none."""
    host = Host("192.0.2.11", "auditor", "fake-login")
    assert host.privilege_level is None
    assert "privilege_level=None" in repr(host)


def test_enable_password_is_optional() -> None:
    """A user that logs in with privilege 15 needs no enable password."""
    host = Host("192.0.2.11", "auditor", "fake-login")
    assert host.enable_password is None


def test_available_commands_start_as_not_checked() -> None:
    """None means not checked, which is different from an empty list."""
    host = Host("192.0.2.11", "auditor", "fake-login")
    assert host.available_commands is None


def test_unknown_host_key_is_not_accepted_by_default() -> None:
    """Trusting an unknown host key without asking must be chosen, never the default."""
    assert Host("192.0.2.11", "auditor", "fake-login").accept_unknown_host_key is False
    assert Host("192.0.2.11", "auditor", "fake-login", accept_unknown_host_key=True).accept_unknown_host_key is True


@pytest.mark.parametrize("value", ["yes", "True", 1, 0, None])
def test_accept_unknown_host_key_must_be_a_bool(value: object) -> None:
    """Only True and False: anything else, as from a damaged hosts.json, is refused."""
    with pytest.raises(ValueError, match="Accept unknown host key"):
        Host("192.0.2.11", "auditor", "fake-login", accept_unknown_host_key=value)  # type: ignore[arg-type]


def test_printing_a_host_hides_its_passwords() -> None:
    """Passwords never show up when a host is printed or formatted."""
    host = Host("192.0.2.11", "auditor", "fake-login", enable_password="fake-enable")
    for text in (repr(host), str(host), f"{host}", repr([host])):
        assert "fake-login" not in text
        assert "fake-enable" not in text


@pytest.mark.parametrize("ip", ["192.0.2.11", "10.0.0.1", "0.0.0.0", "255.255.255.255"])
def test_valid_ipv4_is_accepted(ip: str) -> None:
    """Any IPv4 address in dotted form is a valid host IP."""
    assert Host(ip, "auditor", "fake-login").ip == ip


@pytest.mark.parametrize(
    "ip",
    [
        "",
        "abc",
        "192.0.2.256",  # number too large
        "192.0.2",  # too few parts
        "192.0.2.011",  # leading zero, could be read as octal
        " 192.0.2.11",  # space
        "10.0.0.1; reload",  # command injection
        "2001:db8::1",  # IPv6, not supported yet
        3232235786,  # an int, which ipaddress would otherwise accept
        None,
    ],
)
def test_invalid_ip_raises(ip: object) -> None:
    """Anything that isn't an IPv4 address as text is rejected."""
    with pytest.raises(ValueError):
        Host(ip, "auditor", "fake-login")  # type: ignore[arg-type]


@pytest.mark.parametrize("level", [0, 15])
def test_privilege_level_limits_are_accepted(level: int) -> None:
    """0 and 15 are both valid Cisco privilege levels."""
    assert Host("192.0.2.11", "auditor", "fake-login", privilege_level=level).privilege_level == level


@pytest.mark.parametrize("level", [-1, 16, 1.5, True, "15"])
def test_invalid_privilege_level_raises(level: object) -> None:
    """Only whole numbers from 0 to 15 are privilege levels, not bools, floats or text."""
    with pytest.raises(ValueError):
        Host("192.0.2.11", "auditor", "fake-login", privilege_level=level)  # type: ignore[arg-type]


@pytest.mark.parametrize("username", ["", "   ", None])
def test_empty_username_raises(username: object) -> None:
    """A host needs a username to log in with."""
    with pytest.raises(ValueError):
        Host("192.0.2.11", username, "fake-login")  # type: ignore[arg-type]


@pytest.mark.parametrize("password", ["", None])
def test_empty_password_raises(password: object) -> None:
    """A host needs a password to log in with."""
    with pytest.raises(ValueError):
        Host("192.0.2.11", "auditor", password)  # type: ignore[arg-type]


def test_invalid_ip_error_does_not_show_the_password() -> None:
    """Error messages name the bad value, never the secrets."""
    with pytest.raises(ValueError) as error:
        Host("bad", "auditor", "fake-login", enable_password="fake-enable")
    assert "fake-login" not in str(error.value)
    assert "fake-enable" not in str(error.value)


def test_hostname_starts_as_not_read() -> None:
    """The hostname is read from the device after connecting, so a new host has none."""
    host = Host("192.0.2.11", "auditor", "fake-login")
    assert host.hostname is None


@pytest.mark.parametrize("username", ["admin\nreload", "admin\r", "ad\x00min", "\tadmin"])
def test_username_with_control_character_raises(username: str) -> None:
    """Line breaks, tabs and other control characters are never part of a username."""
    with pytest.raises(ValueError):
        Host("192.0.2.11", username, "fake-login")


@pytest.mark.parametrize("password", ["fake\nreload", "fake\r", "fake\x00"])
def test_password_with_control_character_raises_without_showing_it(password: str) -> None:
    """A line break in a password could send a second command, and the error never shows the password."""
    with pytest.raises(ValueError) as error:
        Host("192.0.2.11", "auditor", password)
    assert "fake" not in str(error.value)


def test_password_with_spaces_is_accepted() -> None:
    """Spaces are printable and can be part of a real password."""
    assert Host("192.0.2.11", "auditor", "fake login").ssh_password == "fake login"


@pytest.mark.parametrize("enable", ["", 5, "fake\nreload"])
def test_invalid_enable_password_raises_without_showing_it(enable: object) -> None:
    """An enable password is None or printable text, and errors never show it."""
    with pytest.raises(ValueError) as error:
        Host("192.0.2.11", "auditor", "fake-login", enable_password=enable)  # type: ignore[arg-type]
    assert "fake" not in str(error.value)


@pytest.mark.parametrize("name", ["SW1", "core-sw-01", "R", "a" * 63])
def test_valid_hostname_is_accepted(name: str) -> None:
    """Names that follow Cisco's rules are accepted."""
    assert is_valid_hostname(name)
    assert Host("192.0.2.11", "auditor", "fake-login", hostname=name).hostname == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "1core",  # starts with a digit
        "-core",  # starts with a hyphen
        "core-",  # ends with a hyphen
        "core sw",  # space
        "core_sw",  # underscore
        "core.lab",  # dot
        "../../evil",  # path, would be dangerous in a file name
        "core\nreload",  # line break
        "kärna",  # not ASCII
        "a" * 64,  # too long
        5,  # not text
    ],
)
def test_invalid_hostname_is_rejected(name: object) -> None:
    """Anything outside Cisco's hostname rules is rejected, by the function and by Host."""
    assert not is_valid_hostname(name)
    with pytest.raises(ValueError):
        Host("192.0.2.11", "auditor", "fake-login", hostname=name)  # type: ignore[arg-type]


def test_available_commands_can_be_an_empty_list() -> None:
    """An empty list means checked, and nothing found. It's different from None."""
    assert Host("192.0.2.11", "auditor", "fake-login", available_commands=[]).available_commands == []


@pytest.mark.parametrize("commands", ["show", ("show",), ["show", 5], [None]])
def test_invalid_available_commands_raise(commands: object) -> None:
    """Available commands are None or a list of text."""
    with pytest.raises(ValueError):
        Host("192.0.2.11", "auditor", "fake-login", available_commands=commands)  # type: ignore[arg-type]
