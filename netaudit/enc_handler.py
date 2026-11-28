"""Encryption of project files: a key made from the project password, and encrypting and decrypting with it."""

import base64
import secrets

from cryptography.fernet import Fernet
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
