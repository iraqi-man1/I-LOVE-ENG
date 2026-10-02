import multiprocessing
import sys


def main() -> int:
    # Required so worker processes start correctly inside the frozen app.
    multiprocessing.freeze_support()
    from pdftoolbox.app import run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
