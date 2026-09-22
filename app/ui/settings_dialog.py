from PySide6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QLineEdit, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QFileDialog, QDialogButtonBox
)

from .. import db, config
from ..ai_providers import get_provider
from .workers import WorkerThread


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الإعدادات")
        self.setMinimumWidth(420)
        self._worker = None

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(config.AI_PROVIDERS)
        self.provider_combo.setCurrentText(db.get_setting("ai_provider", "gemini"))

        self.api_key_edit = QLineEdit(db.get_setting("api_key", ""))
        self.api_key_edit.setEchoMode(QLineEdit.Password)

        self.model_name_edit = QLineEdit(db.get_setting("ai_model", ""))
        self.model_name_edit.setPlaceholderText("مثال: gemini-2.0-flash")

        self.test_btn = QPushButton("اختبار الاتصال")
        self.test_status = QLabel("")
        self.test_btn.clicked.connect(self._test_connection)

        self.whisper_combo = QComboBox()
        self.whisper_combo.addItems(config.WHISPER_MODELS)
        self.whisper_combo.setCurrentText(
            db.get_setting("whisper_model", config.DEFAULT_WHISPER_MODEL)
        )

        self.output_dir_edit = QLineEdit(db.get_setting("output_dir", ""))
        browse_btn = QPushButton("استعراض...")
        browse_btn.clicked.connect(self._browse_output_dir)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_dir_edit)
        out_row.addWidget(browse_btn)

        form = QFormLayout()
        form.addRow("مزود الذكاء الاصطناعي:", self.provider_combo)
        form.addRow("API Key:", self.api_key_edit)
        form.addRow("اسم النموذج:", self.model_name_edit)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_status)
        form.addRow("", test_row)
        form.addRow("نموذج Whisper الافتراضي:", self.whisper_combo)
        form.addRow("مجلد الإخراج:", out_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "اختر مجلد الإخراج")
        if d:
            self.output_dir_edit.setText(d)

    def _test_connection(self):
        provider = get_provider(
            self.provider_combo.currentText(),
            self.api_key_edit.text(),
            self.model_name_edit.text(),
        )
        self.test_btn.setEnabled(False)
        self.test_status.setText("جارٍ الاختبار...")
        self._worker = WorkerThread(provider.test_connection)
        self._worker.finished_ok.connect(self._on_test_result)
        self._worker.failed.connect(lambda msg: self._on_test_result((False, msg)))
        self._worker.start()

    def _on_test_result(self, result):
        ok, msg = result
        self.test_btn.setEnabled(True)
        self.test_status.setText(("✔ نجح الاتصال: " if ok else "✘ فشل: ") + msg)

    def _save(self):
        db.set_setting("ai_provider", self.provider_combo.currentText())
        db.set_setting("api_key", self.api_key_edit.text())
        db.set_setting("ai_model", self.model_name_edit.text())
        db.set_setting("whisper_model", self.whisper_combo.currentText())
        db.set_setting("output_dir", self.output_dir_edit.text())
        self.accept()
