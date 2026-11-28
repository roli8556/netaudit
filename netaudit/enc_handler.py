"""Encryption of project files: a key made from the project password, and encrypting and decrypting with it."""

import base64
import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


SALT_BYTES = 16  # the salt length RFC 9106 recommends
KEY_BYTES = 32  # the key length Fernet needs

# Argon2id settings for new projects: RFC 9106's choice for limited memory.
DEFAULT_ITERATIONS = 3
DEFAULT_MEMORY_KIB = 65536  # 64 MiB
DEFAULT_LANES = 4


class EncHandler:
    """Encrypts and decrypts one project's files. Holds the key, never the password."""

    def __init__(
        self,
        password: str,
        salt: bytes,
        iterations: int = DEFAULT_ITERATIONS,
        memory_kib: int = DEFAULT_MEMORY_KIB,
        lanes: int = DEFAULT_LANES,
    ) -> None:
        """Make the key from the password and salt. Raises ValueError if a value is invalid.

        The password is only used here, it is not kept in the object."""
        key = EncHandler.derive_key(password, salt, iterations, memory_kib, lanes)
        self._fernet = Fernet(key)
        self.salt = salt
        self.iterations = iterations
        self.memory_kib = memory_kib
        self.lanes = lanes

    @classmethod
    def create(cls, password: str) -> "EncHandler":
        """Return a handler for a new project: a new random salt and the default settings."""
        return cls(password, secrets.token_bytes(SALT_BYTES))

    @classmethod
    def load(cls, path: Path, password: str) -> "EncHandler":
        """Return a handler for an existing project, with the salt and Argon2 settings from its salt file at path.

        The file is JSON: {"salt": "<base64>", "iterations": 3, "memory_kib": 65536, "lanes": 4}.
        Raises ValueError naming the file if it is damaged, and FileNotFoundError if it is missing.
        A wrong password is not noticed here: there is nothing to compare it with until a file is decrypted (B3)."""
        text = path.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("it does not contain a salt and settings")
            salt = base64.b64decode(data["salt"], validate=True)  # JSON can't hold bytes, so the salt is base64 text
            iterations = data["iterations"]
            memory_kib = data["memory_kib"]
            lanes = data["lanes"]
        except (ValueError, KeyError, TypeError) as error:  # JSONDecodeError and bad base64 are ValueErrors
            raise ValueError(f"{path} is damaged: {error}") from error
        # Outside the try, so an empty password isn't reported as a damaged file.
        # A salt or setting out of range is refused by derive_key, with a message naming the setting.
        return cls(password, salt, iterations, memory_kib, lanes)

    def encrypt(self, data: bytes, name: str) -> bytes:
        """Return data encrypted as a Fernet token, with name inside it, so decrypt can tell which file it belongs to.

        name is the file's path inside the project, for example "hosts.enc". Raises ValueError if a value is invalid.
        The same data gives a different token every time, as Fernet adds a random part."""
        if not isinstance(data, bytes):
            raise ValueError(f"Data to encrypt must be bytes, got {type(data).__name__}")
        EncHandler.check_name(name)
        return self._fernet.encrypt(name.encode("utf-8") + b"\n" + data)

    def decrypt(self, token: bytes, name: str) -> bytes:
        """Return the data in a token made by encrypt for the same name.

        Raises ValueError if the password is wrong, the token is damaged, or the token belongs to another file.
        Fernet can't tell a wrong password from a damaged token: both just fail its check."""
        if not isinstance(token, bytes):
            raise ValueError(f"Token must be bytes, got {type(token).__name__}")
        EncHandler.check_name(name)
        try:
            plain = self._fernet.decrypt(token)
        except InvalidToken as error:
            raise ValueError("Wrong password, or the file is damaged") from error
        # partition splits at the first line break only, so line breaks in the data are kept.
        stored_name, _, data = plain.partition(b"\n")
        if stored_name != name.encode("utf-8"):
            # The stored name is safe to show: Fernet has proved that we wrote it.
            raise ValueError(f"The data belongs to {stored_name.decode('utf-8')!r}, not {name!r}")
        return data

    @staticmethod
    def check_name(name: str) -> None:
        """Raise ValueError unless name is non-empty text without a line break (the line break ends the name)."""
        if not isinstance(name, str) or not name or "\n" in name:
            raise ValueError(f"File name must be text without line breaks and cannot be empty, got {name!r}")

    @staticmethod
    def derive_key(password: str, salt: bytes, iterations: int, memory_kib: int, lanes: int) -> bytes:
        """Return the Fernet key for this password and salt, made with Argon2id.

        The same values always give the same key. Raises ValueError if a value is invalid, without showing the password."""
        if not isinstance(password, str) or not password:
            raise ValueError("Password must be text and cannot be empty")
        if not isinstance(salt, bytes) or len(salt) < SALT_BYTES:
            raise ValueError(f"Salt must be at least {SALT_BYTES} bytes")
        # Upper limits too, as the settings will be read from a file (B4): a damaged file must not ask for 1 TB of memory.
        # type() is not int also rejects True and False, as in ProjectConfig.
        if type(iterations) is not int or not 1 <= iterations <= 100:
            raise ValueError(f"Argon2 iterations must be a whole number from 1 to 100, got {iterations!r}")
        if type(lanes) is not int or not 1 <= lanes <= 64:
            raise ValueError(f"Argon2 lanes must be a whole number from 1 to 64, got {lanes!r}")
        # Argon2 needs at least 8 KiB per lane. 4194304 KiB = 4 GiB.
        if type(memory_kib) is not int or not 8 * lanes <= memory_kib <= 4194304:
            raise ValueError(f"Argon2 memory must be a whole number of KiB from {8 * lanes} to 4194304, got {memory_kib!r}")
        kdf = Argon2id(salt=salt, length=KEY_BYTES, iterations=iterations, lanes=lanes, memory_cost=memory_kib)
        raw_key = kdf.derive(password.encode("utf-8"))
        return base64.urlsafe_b64encode(raw_key)  # Fernet wants the key as URL-safe base64
