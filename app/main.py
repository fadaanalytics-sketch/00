import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import config, db
from .ui.main_window import MainWindow


def main():
    config.ensure_dirs()
    db.get_conn()
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
