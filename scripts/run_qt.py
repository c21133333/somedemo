import os
import sys


def main():
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")
    if hasattr(sys, "_MEIPASS"):
        repo_root = sys._MEIPASS
    else:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for path in (repo_root, os.path.join(repo_root, "src")):
        if path not in sys.path:
            sys.path.insert(0, path)

    from somedemo.ui_qt.main_window import run

    run()


if __name__ == "__main__":
    main()
