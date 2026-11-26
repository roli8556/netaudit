"""The text menu: the only part of netaudit that talks to the user."""

import sys
from pathlib import Path

from netaudit.project import Project, ProjectConfig

# Names Windows reserves for devices: a folder can't have them, whatever the case.
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{n}" for n in range(1, 10)} | {
    f"LPT{n}" for n in range(1, 10)
}


class Menu:
    """The text menu. The only part of netaudit that uses input(), print() and getpass."""

    def __init__(self) -> None:
        """Start with no project open."""
        self.project: Project | None = None  # the open project, None in the start menu

    def run(self) -> None:
        """Show the start menu until the user exits.

        A ValueError or OSError from an action is shown as an error, and the menu is shown again."""
        print("netaudit")
        while True:
            try:
                keep_going = self.start_menu()
            except (ValueError, OSError) as error:
                print(f"Error: {error}", file=sys.stderr)
                continue
            if not keep_going:
                print("Bye")
                return

    def start_menu(self) -> bool:
        """Show the start menu once and call the chosen action. Return False when the user wants to exit."""
        print()
        print("Start menu")
        print("  1. Create project")
        print("  2. Load project")
        print("  q. Exit")
        choice = self.ask("Choose: ")
        if choice == "1":
            self.create_project_menu()
        elif choice == "2":
            self.load_project_menu()
        elif choice.lower() == "q":  # Q works too
            return False
        else:
            print("Please type 1, 2 or q.", file=sys.stderr)
        return True

    def create_project_menu(self) -> None:
        """Ask for a new project's details, create it in location/name, and open its project menu.

        Raises ValueError for a bad answer and OSError if the folder can't be created (for example
        because it already exists). run shows the error, and nothing is created."""
        print()
        print("Create project")
        name = self.ask("Project name: ")
        if not is_safe_folder_name(name):
            raise ValueError(
                f"{name!r} can't be a folder name: use letters, digits, spaces, - and _ (and not a name like CON)"
            )
        location = Path(self.ask("Location (an existing folder): ")).expanduser()
        if not location.is_dir():
            raise ValueError(f"{location} is not an existing folder")
        port = self.ask_number("SSH port [22]: ", 22)
        timeout = self.ask_number("SSH timeout in seconds [10]: ", 10)
        config = ProjectConfig(name, ssh_port=port, ssh_timeout=timeout)
        self.project = Project.create(location / name, config)
        print(f"Created project {name!r} in {self.project.path}")
        print("WARNING: this project is not encrypted yet. Use fake passwords only.")
        self.project_menu()

    def project_menu(self) -> None:
        """Show the menu of the open project until the user closes it."""
        while self.project is not None:
            print()
            print(f"Project: {self.project.config.name} ({len(self.project.hosts)} hosts)")
            print("  q. Close project")
            choice = self.ask("Choose: ")
            if choice.lower() == "q":
                self.project = None
            else:
                print("Please type q.", file=sys.stderr)

    def load_project_menu(self) -> None:
        """Ask for a project's folder and load it. Not built yet."""
        print("Not available yet.")

    def ask(self, prompt: str) -> str:
        """Ask until the user types something, and return it without spaces at the ends."""
        while True:
            answer = input(prompt).strip()
            if answer:
                return answer
            print("Please type a value.", file=sys.stderr)

    def ask_number(self, prompt: str, default: int) -> int:
        """Ask for a whole number. Enter alone gives the default. Raises ValueError for anything else."""
        answer = input(prompt).strip()
        if not answer:
            return default
        if not answer.isascii() or not answer.isdigit():  # isdigit alone would accept ², which int() refuses
            raise ValueError(f"{answer!r} is not a whole number")
        return int(answer)


def is_safe_folder_name(name: str) -> bool:
    """Return True if name can be used as a folder name on Windows, Linux and macOS.

    Only letters, digits, spaces, - and _, at most 64 characters, no space at either end,
    and not a name Windows reserves (like CON or NUL). So no path parts like .. or C: either."""
    if not 1 <= len(name) <= 64 or name != name.strip():
        return False
    if name.upper() in WINDOWS_RESERVED_NAMES:
        return False
    for character in name:
        if not (character.isalnum() or character in " -_"):
            return False
    return True
