"""A single host in a project."""

import ipaddress
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

    def __post_init__(self) -> None:
        """Check host data for validity. Raises ValueError if invalid."""
        # Type checks come first: 'or' stops at the first true part, so a wrong type never
        # reaches the comparison. type() is not int also rejects True and False, isinstance wouldn't.
        if type(self.privilege_level) is not int or not 0 <= self.privilege_level <= 15:
            raise ValueError(f"Privilege level must be a whole number from 0 to 15, got {self.privilege_level!r}")
        if not isinstance(self.ip, str):
            raise ValueError(f"IP address must be text, got {self.ip!r}")
        try:
            ipaddress.IPv4Address(self.ip)  # IPv4 only for now
        except ValueError as error:
            raise ValueError(f"Invalid IPv4 address: {self.ip!r}") from error
        if not isinstance(self.ssh_username, str) or not self.ssh_username.strip():
            raise ValueError("SSH username cannot be empty")
        if not isinstance(self.ssh_password, str) or not self.ssh_password:
            raise ValueError("SSH password cannot be empty")
