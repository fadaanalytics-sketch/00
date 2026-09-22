"""A single, consistent visual theme for the whole app (colors, fonts, widget styling)."""
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# Font stack: each of these renders Arabic well on its platform (Tahoma/Segoe UI on
# Windows, San Francisco Arabic on macOS), with broadly-available Linux fallbacks.
FONT_FAMILIES = [
    "Segoe UI", "Tahoma", "Noto Sans Arabic", "Noto Sans", "Cantarell",
    "DejaVu Sans", "Liberation Sans", "Arial", "sans-serif",
]
BASE_FONT_SIZE = 10

COLORS = {
    "bg": "#F3F5F9",
    "surface": "#FFFFFF",
    "surface_alt": "#F9FAFB",
    "border": "#DDE1E8",
    "border_light": "#E9ECF2",
    "text": "#1F2430",
    "text_muted": "#6B7280",
    "text_on_primary": "#FFFFFF",
    "primary": "#3B6DF0",
    "primary_hover": "#2F5CD6",
    "primary_pressed": "#254AB0",
    "primary_soft": "#E6ECFD",
    "danger": "#E5484D",
    "danger_hover": "#D33D42",
    "danger_soft": "#FBE7E7",
    "disabled_bg": "#EDEFF3",
    "disabled_text": "#A2A8B4",
}


def _pick_available_font(available=None) -> str:
    if available is None:
        available = set(QFontDatabase.families())
    for family in FONT_FAMILIES:
        if family in available:
            return family
    return QFont().family()


def apply_theme(app: QApplication):
    app.setStyle("Fusion")

    font = QFont(_pick_available_font(), BASE_FONT_SIZE)
    app.setFont(font)

    app.setStyleSheet(_build_stylesheet())


def _build_stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{
        background-color: {c['bg']};
        color: {c['text']};
    }}

    QMainWindow, QDialog {{
        background-color: {c['bg']};
    }}

    QLabel {{
        color: {c['text']};
        background: transparent;
    }}

    QLabel[secondary="true"] {{
        color: {c['text_muted']};
    }}

    /* ---- menu bar / menus ---- */
    QMenuBar {{
        background-color: {c['surface']};
        border-bottom: 1px solid {c['border']};
        padding: 2px 4px;
    }}
    QMenuBar::item {{
        padding: 6px 12px;
        border-radius: 6px;
        background: transparent;
    }}
    QMenuBar::item:selected {{
        background-color: {c['primary_soft']};
        color: {c['primary_pressed']};
    }}
    QMenu {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 24px 8px 12px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background-color: {c['primary_soft']};
        color: {c['primary_pressed']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c['border']};
        margin: 6px 4px;
    }}

    /* ---- buttons ---- */
    QPushButton {{
        background-color: {c['primary']};
        color: {c['text_on_primary']};
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {c['primary_hover']};
    }}
    QPushButton:pressed {{
        background-color: {c['primary_pressed']};
    }}
    QPushButton:disabled {{
        background-color: {c['disabled_bg']};
        color: {c['disabled_text']};
    }}

    QPushButton[flat="true"] {{
        background-color: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border']};
    }}
    QPushButton[flat="true"]:hover {{
        background-color: {c['surface_alt']};
        border-color: {c['primary']};
    }}

    QPushButton[danger="true"] {{
        background-color: {c['surface']};
        color: {c['danger']};
        border: 1px solid {c['danger']};
    }}
    QPushButton[danger="true"]:hover {{
        background-color: {c['danger_soft']};
    }}
    QPushButton[danger="true"]:disabled {{
        background-color: {c['disabled_bg']};
        color: {c['disabled_text']};
        border: 1px solid {c['border']};
    }}

    /* ---- inputs ---- */
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 7px;
        padding: 6px 10px;
        selection-background-color: {c['primary_soft']};
        selection-color: {c['primary_pressed']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {c['primary']};
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        background-color: {c['disabled_bg']};
        color: {c['disabled_text']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        selection-background-color: {c['primary_soft']};
        selection-color: {c['primary_pressed']};
        outline: none;
        padding: 4px;
    }}

    /* ---- tabs ---- */
    QTabWidget::pane {{
        border: 1px solid {c['border']};
        border-radius: 10px;
        background-color: {c['surface']};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {c['text_muted']};
        padding: 10px 18px;
        margin: 0 2px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        color: {c['primary']};
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-bottom: 2px solid {c['primary']};
    }}
    QTabBar::tab:!selected:hover {{
        color: {c['text']};
        background-color: {c['surface_alt']};
    }}

    /* ---- lists / tables ---- */
    QListWidget {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 8px;
        border-radius: 6px;
        margin: 1px 0;
    }}
    QListWidget::item:selected {{
        background-color: {c['primary']};
        color: {c['text_on_primary']};
    }}
    QListWidget::item:!selected:hover {{
        background-color: {c['surface_alt']};
    }}

    QTableWidget {{
        background-color: {c['surface']};
        alternate-background-color: {c['surface_alt']};
        gridline-color: {c['border_light']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        selection-background-color: {c['primary_soft']};
        selection-color: {c['text']};
        outline: none;
    }}
    QHeaderView::section {{
        background-color: {c['surface_alt']};
        color: {c['text_muted']};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {c['border']};
        font-weight: 600;
    }}
    QTableWidget::item {{
        padding: 4px;
    }}

    /* ---- misc containers ---- */
    QGroupBox {{
        border: 1px solid {c['border']};
        border-radius: 10px;
        margin-top: 14px;
        padding-top: 14px;
        font-weight: 600;
        background-color: {c['surface']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {c['text']};
    }}

    QSplitter::handle {{
        background-color: {c['bg']};
        width: 6px;
    }}

    QGraphicsView {{
        background-color: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}

    QStatusBar {{
        background-color: {c['surface']};
        border-top: 1px solid {c['border']};
        color: {c['text_muted']};
    }}

    /* ---- progress bar ---- */
    QProgressBar {{
        background-color: {c['disabled_bg']};
        border: none;
        border-radius: 7px;
        height: 14px;
        text-align: center;
        color: {c['text']};
    }}
    QProgressBar::chunk {{
        background-color: {c['primary']};
        border-radius: 7px;
    }}

    /* ---- checkbox ---- */
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid {c['border']};
        background-color: {c['surface']};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c['primary']};
        border: 1px solid {c['primary']};
    }}

    /* ---- scrollbars ---- */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['border']};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['text_muted']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c['border']};
        border-radius: 5px;
        min-width: 24px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    """
