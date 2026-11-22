"""A single host in a project."""

from dataclasses import dataclass, field


@dataclass
class Host:
    """One switch or router, with what is needed to log in to it over SSH."""

    ip: str
    hostname: str
    username: str
    # repr=False keeps secrets out of print(), logs and error messages
    password: str = field(repr=False)
    enable_password: str | None = field(default=None, repr=False)
