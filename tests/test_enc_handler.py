"""Tests for netaudit/enc_handler.py."""

import base64
import json
from pathlib import Path

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


def write_salt_file(folder: Path, **changes: object) -> Path:
    """Write a valid project.salt with the fast settings, with some values changed, and return its path."""
    data = {"salt": base64.b64encode(SALT).decode("ascii"), **FAST, **changes}
    path = folder / "project.salt"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_reads_salt_and_settings(tmp_path: Path) -> None:
    """The handler gets the salt and settings from the file."""
    handler = EncHandler.load(write_salt_file(tmp_path), PASSWORD)
    assert handler.salt == SALT
    assert (handler.iterations, handler.memory_kib, handler.lanes) == (1, 8, 1)


def test_load_gives_the_same_key_as_the_same_password_and_salt(tmp_path: Path) -> None:
    """What was encrypted with the key from this password and salt can be decrypted after load."""
    token = EncHandler(PASSWORD, SALT, **FAST).encrypt(b"hello", "hosts.enc")
    handler = EncHandler.load(write_salt_file(tmp_path), PASSWORD)
    assert handler.decrypt(token, "hosts.enc") == b"hello"


def test_load_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    """A missing salt file is not damage, so it stays FileNotFoundError, like a missing config.json."""
    with pytest.raises(FileNotFoundError):
        EncHandler.load(tmp_path / "project.salt", PASSWORD)


@pytest.mark.parametrize(
    "text",
    [
        "",  # empty
        "not json",
        "[1, 2]",  # a list, not an object
        '{"iterations": 1, "memory_kib": 8, "lanes": 1}',  # no salt
        '{"salt": "MDEyMzQ1Njc4OWFiY2RlZg==", "memory_kib": 8, "lanes": 1}',  # no iterations
        '{"salt": "not base64!", "iterations": 1, "memory_kib": 8, "lanes": 1}',
        '{"salt": 5, "iterations": 1, "memory_kib": 8, "lanes": 1}',  # salt not text
    ],
)
def test_load_damaged_file_raises_naming_the_file(tmp_path: Path, text: str) -> None:
    """Every kind of damage is a ValueError that names the file."""
    path = tmp_path / "project.salt"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="project.salt is damaged"):
        EncHandler.load(path, PASSWORD)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"salt": base64.b64encode(b"short").decode("ascii")}, "Salt"),
        ({"iterations": 0}, "Argon2 iterations"),
        ({"lanes": "1"}, "Argon2 lanes"),
        ({"memory_kib": 10**12}, "Argon2 memory"),  # a damaged file must not ask for a terabyte
    ],
)
def test_load_refuses_bad_values_from_the_file(tmp_path: Path, changes: dict[str, object], message: str) -> None:
    """Values that are readable but wrong are refused by the same checks as in the constructor."""
    with pytest.raises(ValueError, match=message):
        EncHandler.load(write_salt_file(tmp_path, **changes), PASSWORD)


def test_load_empty_password_is_not_reported_as_damage(tmp_path: Path) -> None:
    """The file is fine, so the error is about the password."""
    with pytest.raises(ValueError, match="Password") as error:
        EncHandler.load(write_salt_file(tmp_path), "")
    assert "damaged" not in str(error.value)


@pytest.fixture
def handler() -> EncHandler:
    """A handler with the fast settings, for the encrypt and decrypt tests."""
    return EncHandler(PASSWORD, SALT, **FAST)


@pytest.mark.parametrize("data", [b"hello", b"", b"line 1\nline 2\n", bytes(range(256))])
def test_decrypt_gives_back_what_was_encrypted(handler: EncHandler, data: bytes) -> None:
    """Any bytes come back unchanged, also empty data and data with line breaks."""
    assert handler.decrypt(handler.encrypt(data, "hosts.enc"), "hosts.enc") == data


def test_token_does_not_show_the_data(handler: EncHandler) -> None:
    """The token is encrypted, so neither the data nor the name can be read from it."""
    token = handler.encrypt(b"fake-device-password", "hosts.enc")
    assert b"fake-device-password" not in token
    assert b"hosts.enc" not in token


def test_same_data_gives_a_different_token_each_time(handler: EncHandler) -> None:
    """Fernet adds a random part, so two files with the same content don't look the same."""
    assert handler.encrypt(b"hello", "hosts.enc") != handler.encrypt(b"hello", "hosts.enc")


def test_decrypt_with_another_name_raises(handler: EncHandler) -> None:
    """A token copied over another file is refused: this is what binds a file to its path."""
    token = handler.encrypt(b"hello", "hosts.enc")
    with pytest.raises(ValueError, match="belongs to 'hosts.enc', not 'config.enc'"):
        handler.decrypt(token, "config.enc")


def test_decrypt_with_a_name_that_only_starts_the_same_raises(handler: EncHandler) -> None:
    """The whole name must match, not just its start."""
    token = handler.encrypt(b"hello", "hosts.enc")
    with pytest.raises(ValueError, match="belongs to"):
        handler.decrypt(token, "hosts")


def test_decrypt_with_the_wrong_password_raises(handler: EncHandler) -> None:
    """A wrong password gives another key, and the token fails Fernet's check."""
    token = handler.encrypt(b"hello", "hosts.enc")
    wrong = EncHandler("wrong-password", SALT, **FAST)
    with pytest.raises(ValueError, match="Wrong password, or the file is damaged"):
        wrong.decrypt(token, "hosts.enc")


def test_decrypt_damaged_token_raises(handler: EncHandler) -> None:
    """Changing one character anywhere is noticed."""
    token = handler.encrypt(b"hello", "hosts.enc")
    middle = len(token) // 2
    changed = b"A" if token[middle:middle + 1] != b"A" else b"B"
    damaged = token[:middle] + changed + token[middle + 1:]
    with pytest.raises(ValueError, match="Wrong password, or the file is damaged"):
        handler.decrypt(damaged, "hosts.enc")


@pytest.mark.parametrize("token", [b"", b"not a token", b"gAAAAA"])
def test_decrypt_garbage_raises(handler: EncHandler, token: bytes) -> None:
    """Bytes that were never a token give the same error as a damaged one."""
    with pytest.raises(ValueError, match="Wrong password, or the file is damaged"):
        handler.decrypt(token, "hosts.enc")


@pytest.mark.parametrize("name", ["", "hosts\n.enc", None, b"hosts.enc"])
def test_invalid_name_raises(handler: EncHandler, name: object) -> None:
    """A name is non-empty text without a line break, for both encrypt and decrypt."""
    with pytest.raises(ValueError, match="File name"):
        handler.encrypt(b"hello", name)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="File name"):
        handler.decrypt(handler.encrypt(b"hello", "hosts.enc"), name)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["hello", None, 5])
def test_encrypt_and_decrypt_only_take_bytes(handler: EncHandler, value: object) -> None:
    """Text must be encoded to bytes first, so it's always clear which encoding was used."""
    with pytest.raises(ValueError, match="must be bytes"):
        handler.encrypt(value, "hosts.enc")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be bytes"):
        handler.decrypt(value, "hosts.enc")  # type: ignore[arg-type]
