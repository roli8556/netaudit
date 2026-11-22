"""Tests for netaudit/host.py."""

from netaudit.host import Host


def test_host_stores_its_fields() -> None:
    """A host keeps everything it was given."""
    host = Host("192.0.2.11", "core", "auditor", "fake-login", "fake-enable", 15)
    assert host.ip == "192.0.2.11"
    assert host.hostname == "core"
    assert host.ssh_username == "auditor"
    assert host.ssh_password == "fake-login"
    assert host.enable_password == "fake-enable"
    assert host.privilege_level == 15


def test_privilege_level_defaults_to_1() -> None:
    """A host gets the lowest normal level unless told otherwise."""
    host = Host("192.0.2.11", "core", "auditor", "fake-login")
    assert host.privilege_level == 1
    assert "privilege_level=1" in repr(host)


def test_enable_password_is_optional() -> None:
    """A user that logs in with privilege 15 needs no enable password."""
    host = Host("192.0.2.11", "core", "auditor", "fake-login")
    assert host.enable_password is None


def test_available_commands_start_as_not_checked() -> None:
    """None means not checked, which is different from an empty list."""
    host = Host("192.0.2.11", "core", "auditor", "fake-login")
    assert host.available_commands is None


def test_printing_a_host_hides_its_passwords() -> None:
    """Passwords never show up when a host is printed or formatted."""
    host = Host("192.0.2.11", "core", "auditor", "fake-login", "fake-enable")
    for text in (repr(host), str(host), f"{host}", repr([host])):
        assert "fake-login" not in text
        assert "fake-enable" not in text
