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
        """Show the start menu once and call the chosen action. Return False when the user wants to exit."""
        print()
        print("Start menu")
        print("  1. Create project")
        print("  2. Load project")
        print("  3. Exit")
        choice = self.ask("Choose: ")
        if choice == "1":
            self.create_project_menu()
        elif choice == "2":
            self.load_project_menu()
        elif choice == "3":
            return False
        else:
            print("Please type a number from 1 to 3.", file=sys.stderr)
        return True

    def create_project_menu(self) -> None:
        """Ask for a new project's details and create it. Not built yet."""
        print("Not available yet.")

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
