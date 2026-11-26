"""The text menu: the only part of netaudit that talks to the user."""

import sys

from netaudit.project import Project


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
        """Show the start menu once and act on the choice. Return False when the user wants to exit."""
        choice = self.choose("Start menu", ["Create project", "Load project", "Exit"])
        if choice == 3:
            return False
        print("Not available yet.")
        return True

    def ask(self, prompt: str) -> str:
        """Ask until the user types something, and return it without spaces at the ends."""
        while True:
            answer = input(prompt).strip()
            if answer:
                return answer
            print("Please type a value.", file=sys.stderr)

    def choose(self, title: str, options: list[str]) -> int:
        """Show numbered options and ask until one is chosen. Return its number, starting at 1."""
        print()
        print(title)
        for number, option in enumerate(options, start=1):
            print(f"  {number}. {option}")
        valid = [str(number) for number in range(1, len(options) + 1)]
        while True:
            answer = input("Choose: ").strip()
            if answer in valid:
                return int(answer)
            print(f"Please type a number from 1 to {len(options)}.", file=sys.stderr)
