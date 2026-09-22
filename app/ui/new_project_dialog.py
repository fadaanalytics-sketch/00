from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QPushButton, QHBoxLayout,
    QVBoxLayout, QDialogButtonBox, QFileDialog, QStackedWidget, QWidget
)

from .. import config, db


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("مشروع جديد")
        self.setMinimumWidth(420)

        self.name_edit = QLineEdit()

        self.source_combo = QComboBox()
        self.source_combo.addItems(["ملف من الجهاز", "رابط YouTube", "رابط Google Drive"])
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)

        self.file_edit = QLineEdit()
        browse_btn = QPushButton("استعراض...")
        browse_btn.setProperty("flat", "true")
        browse_btn.clicked.connect(self._browse_file)
        file_row = QWidget()
        file_row_l = QHBoxLayout(file_row)
        file_row_l.setContentsMargins(0, 0, 0, 0)
        file_row_l.setSpacing(8)
        file_row_l.addWidget(self.file_edit)
        file_row_l.addWidget(browse_btn)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://...")

        self.stack = QStackedWidget()
        self.stack.addWidget(file_row)
        self.stack.addWidget(self.url_edit)
        self.stack.addWidget(self.url_edit)

        self.whisper_combo = QComboBox()
        self.whisper_combo.addItems(config.WHISPER_MODELS)
        self.whisper_combo.setCurrentText(
            db.get_setting("whisper_model", config.DEFAULT_WHISPER_MODEL)
        )

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("اسم المشروع:", self.name_edit)
        form.addRow("مصدر الفيديو:", self.source_combo)
        form.addRow("", self.stack)
        form.addRow("نموذج Whisper:", self.whisper_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("إنشاء")
        buttons.button(QDialogButtonBox.Cancel).setText("إلغاء")
        buttons.button(QDialogButtonBox.Cancel).setProperty("flat", "true")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.result_data = None

    def _on_source_changed(self, idx):
        self.stack.setCurrentIndex(idx)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر ملف فيديو", "", "Video Files (*.mp4 *.mkv *.mov *.avi *.webm)"
        )
        if path:
            self.file_edit.setText(path)

    def _accept(self):
        idx = self.source_combo.currentIndex()
        source_type = ["local", "youtube", "gdrive"][idx]
        source_value = self.file_edit.text() if idx == 0 else self.url_edit.text()
        if not self.name_edit.text().strip() or not source_value.strip():
            return
        self.result_data = {
            "name": self.name_edit.text().strip(),
            "source_type": source_type,
            "source_value": source_value.strip(),
            "whisper_model": self.whisper_combo.currentText(),
        }
        self.accept()
