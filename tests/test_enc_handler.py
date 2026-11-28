"""Tests for netaudit/enc_handler.py."""

import pytest
from cryptography.fernet import Fernet

from netaudit.enc_handler import DEFAULT_ITERATIONS, DEFAULT_LANES, DEFAULT_MEMORY_KIB, SALT_BYTES, EncHandler


# Tiny Argon2 settings, so the tests are fast. Real projects use the defaults.
FAST = {"iterations": 1, "memory_kib": 8, "lanes": 1}
SALT = b"0123456789abcdef"  # 16 bytes
PASSWORD = "fake-project-password"


def test_same_password_and_salt_give_the_same_key() -> None:
    """This is what makes loading work: the same password gives back the same key."""
    assert EncHandler.derive_key(PASSWORD, SALT, **FAST) == EncHandler.derive_key(PASSWORD, SALT, **FAST)


def test_different_salt_gives_a_different_key() -> None:
    """The same password in two projects gives two different keys."""
    other_salt = b"fedcba9876543210"
    assert EncHandler.derive_key(PASSWORD, SALT, **FAST) != EncHandler.derive_key(PASSWORD, other_salt, **FAST)


def test_different_password_gives_a_different_key() -> None:
    """Even a one-character difference gives a different key."""
    assert EncHandler.derive_key(PASSWORD, SALT, **FAST) != EncHandler.derive_key(PASSWORD + "x", SALT, **FAST)


def test_key_works_with_fernet() -> None:
    """The key has the format Fernet expects, and encrypts and decrypts."""
    fernet = Fernet(EncHandler.derive_key(PASSWORD, SALT, **FAST))
    assert fernet.decrypt(fernet.encrypt(b"hello")) == b"hello"


def test_handler_keeps_salt_and_settings() -> None:
    """These are needed to save project.salt (B4)."""
    handler = EncHandler(PASSWORD, SALT, **FAST)
    assert handler.salt == SALT
    assert handler.iterations == 1
    assert handler.memory_kib == 8
    assert handler.lanes == 1


def test_handler_does_not_keep_the_password() -> None:
    """No attribute holds the password, and printing the handler doesn't show it."""
    handler = EncHandler(PASSWORD, SALT, **FAST)
    assert PASSWORD not in str(vars(handler))
    assert PASSWORD not in repr(handler)


def test_create_uses_a_new_salt_and_the_default_settings() -> None:
    """Each new project gets its own random salt. This test uses the real settings once."""
    first = EncHandler.create(PASSWORD)
    second = EncHandler.create(PASSWORD)
    assert len(first.salt) == SALT_BYTES
    assert first.salt != second.salt
    assert (first.iterations, first.memory_kib, first.lanes) == (DEFAULT_ITERATIONS, DEFAULT_MEMORY_KIB, DEFAULT_LANES)


@pytest.mark.parametrize("password", ["", None, 5, b"fake-bytes"])
def test_invalid_password_raises(password: object) -> None:
    """The password must be text that isn't empty."""
    with pytest.raises(ValueError, match="Password"):
        EncHandler(password, SALT, **FAST)  # type: ignore[arg-type]


@pytest.mark.parametrize("salt", [b"", b"0123456789abcde", "0123456789abcdef", None])
def test_invalid_salt_raises_without_showing_the_password(salt: object) -> None:
    """The salt must be at least 16 bytes. Text is not bytes, even if it looks the same."""
    with pytest.raises(ValueError, match="Salt") as error:
        EncHandler(PASSWORD, salt, **FAST)  # type: ignore[arg-type]
    assert PASSWORD not in str(error.value)


@pytest.mark.parametrize(
    "setting, value",
    [
        ("iterations", 0),
        ("iterations", 101),
        ("iterations", True),  # a bool is an int in Python
        ("iterations", 1.5),
        ("lanes", 0),
        ("lanes", 65),
        ("lanes", "1"),
        ("memory_kib", 7),  # less than 8 KiB per lane
        ("memory_kib", 4194305),  # more than 4 GiB
        ("memory_kib", None),
    ],
)
def test_invalid_setting_raises(setting: str, value: object) -> None:
    """Each setting must be a whole number within its limits."""
    settings = {**FAST, setting: value}
    with pytest.raises(ValueError, match="Argon2"):
        EncHandler(PASSWORD, SALT, **settings)
