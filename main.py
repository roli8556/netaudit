"""Entry point for netaudit."""

from netaudit.menu import Menu


def main() -> None:
    """Start the menu. Ctrl+C or the end of input ends the program without a traceback."""
    try:
        Menu().run()
    except (KeyboardInterrupt, EOFError):
        print("\nBye")


if __name__ == "__main__":
    main()
