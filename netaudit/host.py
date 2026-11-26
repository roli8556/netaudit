"""A single host in a project."""

import ipaddress
from dataclasses import dataclass, field


@dataclass
class Host:
    """One switch or router, with what is needed to log in to it over SSH."""

    ip: str
    ssh_username: str
    # repr=False keeps secrets out of print(), logs and error messages
    ssh_password: str = field(repr=False)
    hostname: str | None = None  # None until read from the device by the parser
    enable_password: str | None = field(default=None, repr=False)
    privilege_level: int | None = None  # what the SSH user gets at login (0-15), None until read from the device
    # What the device says this login can run. Information only: never send commands taken from it
    available_commands: list[str] | None = None  # None means not checked yet

    def __post_init__(self) -> None:
        """Check host data for validity. Raises ValueError if invalid."""
        # Type checks come first: 'or' stops at the first true part, so a wrong type never
        # reaches the comparison. type() is not int also rejects True and False, isinstance wouldn't.
        # None means not read yet, so only a level that is set is checked.
        level = self.privilege_level
        if level is not None and (type(level) is not int or not 0 <= level <= 15):
            raise ValueError(f"Privilege level must be a whole number from 0 to 15, got {self.privilege_level!r}")
        if not isinstance(self.ip, str):
            raise ValueError(f"IP address must be text, got {self.ip!r}")
        try:
            ipaddress.IPv4Address(self.ip)  # IPv4 only for now
        except ValueError as error:
            raise ValueError(f"Invalid IPv4 address: {self.ip!r}") from error
        if not isinstance(self.ssh_username, str) or not self.ssh_username.strip():
            raise ValueError("SSH username cannot be empty")
        if not self.ssh_username.isprintable():
            raise ValueError(f"SSH username contains a control character: {self.ssh_username!r}")
        # Passwords are typed into the device's CLI, so a line break in one could send a second command.
        # The messages never show the password itself.
        if not isinstance(self.ssh_password, str) or not self.ssh_password:
            raise ValueError("SSH password cannot be empty")
        if not self.ssh_password.isprintable():
            raise ValueError("SSH password contains a control character, such as a line break")
        if self.enable_password is not None:
            if not isinstance(self.enable_password, str) or not self.enable_password:
                raise ValueError("Enable password must be text, or None for no enable password")
            if not self.enable_password.isprintable():
                raise ValueError("Enable password contains a control character, such as a line break")
        if self.hostname is not None and not is_valid_hostname(self.hostname):
            raise ValueError(f"Invalid hostname: {self.hostname!r}")
        if self.available_commands is not None:
            if not isinstance(self.available_commands, list):
                raise ValueError(f"Available commands must be a list, got {self.available_commands!r}")
            for command in self.available_commands:
                if not isinstance(command, str):
                    raise ValueError(f"Available commands must be text, got {command!r}")


def is_valid_hostname(name: object) -> bool:
    """Return True if name follows Cisco's hostname rules.

    It must start with a letter, end with a letter or digit, contain only the letters a-z and A-Z,
    digits and hyphens, and be at most 63 characters. Also for the parser, as device output is untrusted."""
    if not isinstance(name, str) or not 1 <= len(name) <= 63:
        return False
    if not name.isascii():  # isalpha() and isalnum() would also accept letters like å
        return False
    if not name[0].isalpha() or not name[-1].isalnum():
        return False
    for character in name:
        if not (character.isalnum() or character == "-"):
            return False
    return True
