"""Thin QMessageBox wrappers with Arabic button labels (Qt's built-ins default to English)."""
from PySide6.QtWidgets import QMessageBox


def _exec_with_ok(icon, parent, title: str, text: str):
    box = QMessageBox(icon, title, text, QMessageBox.Ok, parent)
    box.button(QMessageBox.Ok).setText("موافق")
    box.exec()


def info(parent, title: str, text: str):
    _exec_with_ok(QMessageBox.Information, parent, title, text)


def warn(parent, title: str, text: str):
    _exec_with_ok(QMessageBox.Warning, parent, title, text)


def error(parent, title: str, text: str):
    _exec_with_ok(QMessageBox.Critical, parent, title, text)


def confirm(parent, title: str, text: str) -> bool:
    box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.Yes | QMessageBox.No, parent)
    box.button(QMessageBox.Yes).setText("نعم")
    box.button(QMessageBox.No).setText("لا")
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes
