import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import config, db
from .logging_setup import setup_logging
from .ui.main_window import MainWindow


def main():
    config.ensure_dirs()
    setup_logging()
    db.get_conn()
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
