"""Fixtures shared by several test files. pytest reads this file by itself, so tests don't import it."""

import pytest

import netaudit.enc_handler
from netaudit.enc_handler import EncHandler


# The password of every project the tests create.
PROJECT_PASSWORD = "fake-project-password"


@pytest.fixture
def enc_handler() -> EncHandler:
    """A handler with a fixed salt and tiny Argon2 settings, so tests are fast."""
    return EncHandler(PROJECT_PASSWORD, b"0123456789abcdef", iterations=1, memory_kib=8, lanes=1)


@pytest.fixture
def fast_argon2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make new projects use tiny Argon2 settings instead of 64 MiB, so tests that create projects are fast.

    EncHandler.create reads these constants each time it runs, so changing them here is enough."""
    monkeypatch.setattr(netaudit.enc_handler, "DEFAULT_ITERATIONS", 1)
    monkeypatch.setattr(netaudit.enc_handler, "DEFAULT_MEMORY_KIB", 8)
    monkeypatch.setattr(netaudit.enc_handler, "DEFAULT_LANES", 1)
