"""A single host in a project."""

from dataclasses import dataclass, field


@dataclass
class Host:
    """One switch or router, with what is needed to log in to it over SSH."""

    ip: str
    hostname: str
    ssh_username: str
    # repr=False keeps secrets out of print(), logs and error messages
    ssh_password: str = field(repr=False)
    enable_password: str | None = field(default=None, repr=False)
    privilege_level: int = 1  # what the SSH user gets at login (0-15), 1 is the Cisco default
    # What the device says this login can run. Information only: never send commands taken from it
    available_commands: list[str] | None = None  # None means not checked yet
