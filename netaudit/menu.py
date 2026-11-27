"""The text menu: the only part of netaudit that talks to the user."""

from datetime import datetime
import sys
from enum import Enum
from getpass import getpass
from pathlib import Path

from netaudit.host import Host
from netaudit.log import LogEntry, LogFilter, LogLevel, LogCategory
from netaudit.project import Project, ProjectConfig, ProjectIssue

# Shown after creating or loading a project, until part B encrypts the files.
NOT_ENCRYPTED_WARNING = "WARNING: this project is not encrypted yet. Use fake passwords only."

# Rows per page in print_as_pages.
PAGE_SIZE = 20

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
        print(NOT_ENCRYPTED_WARNING)
        self.project_menu()

    def project_menu(self) -> None:
        """Show the menu of the open project until the user closes it."""
        while self.project is not None:
            print()
            print(f"Project: {self.project.config.name} ({len(self.project.hosts)} hosts)")
            print("  1. Show hosts")
            print("  2. Add host")
            print("  3. Remove host")
            print("  4. Show log")
            print("  q. Close project")
            choice = self.ask("Choose: ")
            # Caught here, not in run, so an error keeps the user in the project menu with the project open
            try:
                if choice == "1":
                    self.show_hosts()
                elif choice == "2":
                    self.add_host_menu()
                elif choice == "3":
                    self.remove_host_menu()
                elif choice == "4":
                    self.show_log_menu()
                elif choice.lower() == "q":
                    self.project = None
                else:
                    print("Please type 1, 2, 3, 4 or q.", file=sys.stderr)
            except (ValueError, OSError) as error:
                print(f"Error: {error}", file=sys.stderr)

    def show_hosts(self) -> None:
        """Print the open project's hosts as a table, numbered from 1 in list order.

        The numbers are only for this list (remove host asks for one), they aren't stored.
        Passwords are never shown, only whether there is an enable password."""
        print()
        if not self.project.hosts:
            print("No hosts yet.")
            return
        print(
            f"{'#':<4}{'IP':<17}{'Username':<17}{'Hostname':<17}{'Privilege':<11}{'Enable password':<17}"
            "Accept unknown key"
        )
        for number, host in enumerate(self.project.hosts, start=1):
            # None means not read from the device yet. The hostname is device text, but Host only accepts valid ones.
            hostname = host.hostname if host.hostname is not None else "-"
            level = str(host.privilege_level) if host.privilege_level is not None else "-"
            enable = "set" if host.enable_password is not None else "not set"
            accept_key = "yes" if host.accept_unknown_host_key else "no"
            print(f"{number:<4}{host.ip:<17}{host.ssh_username:<17}{hostname:<17}{level:<11}{enable:<17}{accept_key}")

    def show_log_menu(self) -> None:
        """Show the log menu of the open project until the user goes back. Only reads the log in memory.

        The filters start empty every time the menu opens, and Show only shows the entries that match them."""
        filters = LogFilter()
        while True:
            title = f"Log ({len(self.project.log.entries)} total entries)"
            if filters:  # at least one filter is set (LogFilter.__bool__)
                filtered_entries = self.project.log.find(
                    level=filters.level,
                    category=filters.category,
                    text=filters.text,
                    since=filters.since,
                    from_number=filters.from_number,
                    to_number=filters.to_number,
                )
                title += f" -> {len(filtered_entries)} match"
            level = filters.level.value if filters.level is not None else "any"
            print()
            print(title)
            print("  1. Show")
            print(f"  2. Level ({level})")
            print(f"  3. Category ({filters.category.value if filters.category is not None else 'any'})")
            print(f"  4. Message ({filters.text if filters.text is not None else 'any'})")
            print(f"  5. Number Range ({filters.from_number if filters.from_number is not None else 'any'} to {filters.to_number if filters.to_number is not None else 'any'})")
            print(f"  6. Since Date/Time ({filters.since.strftime('%Y-%m-%d %H:%M:%S') if filters.since is not None else 'any'})")
            print("  q. Back")
            choice = self.ask("Choose: ")
            if choice == "1":
                if filters:
                    self.show_log(filtered_entries)
                else:
                    self.show_log(self.project.log.entries)
            elif choice == "2":
                filters.level = self.choose_from_enum("Level", LogLevel)
            elif choice == "3":
                filters.category = self.choose_from_enum("Category", LogCategory)   
            elif choice == "4":
                filters.text = input("Message: ").strip() or None
            elif choice == "5":
                # Both are asked before checking, and nothing changes unless both are fine.
                from_number = input("From number (Enter for any): ").strip()
                to_number = input("To number (Enter for any): ").strip()
                if from_number and not (from_number.isascii() and from_number.isdigit()):
                    print(f"Error: {from_number!r} is not a whole number. Nothing changed.", file=sys.stderr)
                elif to_number and not (to_number.isascii() and to_number.isdigit()):
                    print(f"Error: {to_number!r} is not a whole number. Nothing changed.", file=sys.stderr)
                elif from_number and to_number and int(from_number) > int(to_number):
                    print(f"Error: from ({from_number}) is bigger than to ({to_number}). Nothing changed.", file=sys.stderr)
                else:
                    filters.from_number = int(from_number) if from_number else None
                    filters.to_number = int(to_number) if to_number else None
            elif choice == "6":
                since_date = input("Since (YYYY-MM-DD HH:MM:SS, Enter for any): ").strip()
                if not since_date:
                    filters.since = None
                else:
                    try:
                        filters.since = datetime.strptime(since_date, "%Y-%m-%d %H:%M:%S")
                    except ValueError:  # caught here, so a typo keeps the other filters and the log menu
                        print("Invalid date format. Please use YYYY-MM-DD HH:MM:SS.", file=sys.stderr)
            elif choice.lower() == "q":
                return
            else:
                print("Please type 1, 2, 3, 4, 5, 6 or q.", file=sys.stderr)

    def choose_from_enum(self, title: str, enum_class: type[Enum]) -> Enum | None:
        """Print the members of enum_class numbered from 1 and return the one chosen.

        Enter returns None (any). Any other answer that isn't a listed number asks again."""
        members = list(enum_class)  # the members in the order they are defined
        print()
        print(title)
        for number, member in enumerate(members, start=1):
            print(f"  {number}. {member.value}")
        while True:
            answer = input("Number (Enter for any): ").strip()
            if answer == "":
                return None
            if answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(members):
                return members[int(answer) - 1]
            print(f"Please type a number from 1 to {len(members)}, or press Enter.", file=sys.stderr)

    def show_log(self, entries: list[LogEntry]) -> None:
        """Print these log entries in the order given, as a table, a page at a time with print_as_pages.

        Entries without a number (warnings about damaged lines, never in the file) show - as number.
        Messages go through make_printable, since they can contain device text."""
        print()
        if not entries:
            print("No log entries to show.")
            return
        header = f"{'#':<6}{'Time':<21}{'Level':<10}{'Category':<10}Message"
        rows = []
        for entry in entries:
            number = str(entry.number) if entry.number is not None else "-"
            time = entry.time.strftime("%Y-%m-%d %H:%M:%S")  # to the second, the file keeps the full time
            level = entry.level.value
            category = entry.category.value
            rows.append(f"{number:<6}{time:<21}{level:<10}{category:<10}{make_printable(entry.message)}")
        self.print_as_pages(header, rows)

    def print_as_pages(self, header: str, rows: list[str]) -> None:
        """Print the header and rows one page of PAGE_SIZE rows at a time, like the more command.

        After every page but the last, Enter shows the next page and q goes back.
        Any other answer asks again. The header is repeated on every page."""
        for start in range(0, len(rows), PAGE_SIZE):
            print(header)
            for row in rows[start : start + PAGE_SIZE]:
                print(row)
            shown = min(start + PAGE_SIZE, len(rows))
            if shown == len(rows):
                return  # last page: nothing more to ask
            while True:
                answer = input(f"-- More ({shown} of {len(rows)}) -- Enter for more, q to go back: ").strip().lower()
                if answer == "":
                    break  # out of the while: on to the next page
                if answer == "q":
                    return
                print("Please press Enter or type q.", file=sys.stderr)

    def add_host_menu(self) -> None:
        """Ask for a new host's IP, SSH login, enable password and host key choice, and add it to the open project.

        Enter at the enable password means the host has none (None).
        Raises ValueError for a bad answer or an IP that is already in the project (Host and
        add_host check them), and OSError if hosts.json can't be saved. Nothing is added then."""
        print()
        print("Add host")
        ip = self.ask("IP address: ")
        username = self.ask("SSH username: ")
        password = getpass("SSH password: ")  # not stripped: spaces can be part of a password
        # Host refuses "" on purpose, so Enter has to become None here. Not stripped either.
        enable_password = getpass("Enable password (Enter for none): ") or None
        answer = input("Accept an unknown SSH host key without asking? [y/N]: ").strip().lower()
        if answer not in ("", "y", "n"):
            raise ValueError(f"{answer!r} is not y or n")
        host = Host(
            ip, username, password, enable_password=enable_password, accept_unknown_host_key=(answer == "y")
        )
        self.project.add_host(host)
        print(f"Added host {host.ip}")

    def remove_host_menu(self) -> None:
        """Show the hosts, ask for the number of one, confirm, and remove it from the open project.

        q goes back and Enter or n at the confirmation keeps the host. Raises ValueError for a
        number that isn't in the list or an answer that isn't y or n, and OSError if hosts.json
        can't be saved. Nothing is removed then."""
        hosts = self.project.hosts
        if not hosts:
            print()
            print("No hosts to remove.")
            return
        self.show_hosts()
        answer = self.ask("Number of the host to remove (q to go back): ")
        if answer.lower() == "q":
            return
        # isascii first: isdigit alone would accept ², which int() refuses
        if not answer.isascii() or not answer.isdigit() or not 1 <= int(answer) <= len(hosts):
            raise ValueError(f"{answer!r} is not a host number from 1 to {len(hosts)}")
        host = hosts[int(answer) - 1]  # the list shows 1, 2, 3..., the list index starts at 0
        confirm = input(f"Remove {host.ip}? Its login is deleted too. [y/N]: ").strip().lower()
        if confirm not in ("", "y", "n"):
            raise ValueError(f"{confirm!r} is not y or n")
        if confirm != "y":
            print("Nothing removed.")
            return
        self.project.remove_host(host.ip)
        print(f"Removed host {host.ip}")

    def load_project_menu(self) -> None:
        """Ask for a project's folder, load it, deal with its issues, and open its project menu.

        Raises ValueError for a folder that isn't a project or a damaged project file. run shows the
        error, and no project is opened."""
        print()
        print("Load project")
        path = Path(self.ask("Project folder: ")).expanduser()
        if not path.is_dir():
            raise ValueError(f"{path} is not a folder")
        if not (path / "config.json").is_file():
            raise ValueError(f"{path} is not a netaudit project (it has no config.json)")
        project = Project.load(path)
        print(f"Loaded project {project.config.name!r} ({len(project.hosts)} hosts)")
        print(NOT_ENCRYPTED_WARNING)
        if not self.missing_folders_menu(project):
            return  # the user chose to close the project
        self.project = project  # only now, so a failure above never leaves a half-opened project
        self.project_menu()

    def missing_folders_menu(self, project: Project) -> bool:
        """If project folders are missing, ask what to do. Return False if the user wants to close the project."""
        if ProjectIssue.MISSING_FOLDER not in project.issues:
            return True
        folders = project.issues[ProjectIssue.MISSING_FOLDER]
        while True:
            print()
            print("These project folders are missing: " + ", ".join(folders))
            print("  1. Create them")
            print("  2. Continue without them")
            print("  q. Close the project")
            choice = self.ask("Choose: ")
            if choice == "1":
                project.create_missing_folders()
                print("Created the missing folders.")
                return True
            if choice == "2":
                return True
            if choice.lower() == "q":
                return False
            print("Please type 1, 2 or q.", file=sys.stderr)

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


def make_printable(text: str) -> str:
    """Return text with every character that isn't printable shown as its escape code, like \n or \x1b.

    Use it on device text and log messages before printing them: a line break could fake an extra
    line, and an escape character (\x1b) could send control codes to the terminal."""
    result = []
    for character in text:
        if character.isprintable():
            result.append(character)
        else:
            # repr("\n") is the 4 characters '\n' with the quotes, [1:-1] cuts the quotes off.
            result.append(repr(character)[1:-1])
    return "".join(result)
