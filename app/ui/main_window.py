import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QListWidget, QListWidgetItem, QSplitter, QTabWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox, QCheckBox,
    QFileDialog, QAbstractItemView
)

from .. import config, db
from ..models import Project, Topic
from .. import video_sources, transcription, analysis, exporter, ai_providers
from .new_project_dialog import NewProjectDialog
from .settings_dialog import SettingsDialog
from .template_editor import TemplatesManagerDialog
from .workers import WorkerThread


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Video Analyzer & Smart Clip Generator")
        self.resize(1200, 800)

        self.current_project: Project = None
        self.current_segments = []
        self.current_topics: list[Topic] = []
        self._worker = None

        self._build_menu()
        self._build_central()
        self.refresh_project_list()

    # ---------------- menu ----------------

    def _build_menu(self):
        menu = self.menuBar()
        project_menu = menu.addMenu("مشروع")
        new_action = project_menu.addAction("مشروع جديد")
        new_action.triggered.connect(self.on_new_project)
        delete_action = project_menu.addAction("حذف المشروع الحالي")
        delete_action.triggered.connect(self.on_delete_project)

        settings_menu = menu.addMenu("الإعدادات")
        settings_action = settings_menu.addAction("إعدادات التطبيق...")
        settings_action.triggered.connect(self.on_open_settings)

        templates_menu = menu.addMenu("القوالب")
        templates_action = templates_menu.addAction("إدارة القوالب...")
        templates_action.triggered.connect(self.on_open_templates)

    # ---------------- layout ----------------

    def _build_central(self):
        splitter = QSplitter()

        self.project_list = QListWidget()
        self.project_list.currentRowChanged.connect(self.on_project_selected)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel("المشاريع"))
        left_l.addWidget(self.project_list)
        left.setMaximumWidth(280)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_transcribe_tab(), "الفيديو والتفريغ الصوتي")
        self.tabs.addTab(self._build_analysis_tab(), "تحليل الذكاء الاصطناعي")
        self.tabs.addTab(self._build_export_tab(), "التصدير")

        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def _build_transcribe_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        self.project_info_label = QLabel("لا يوجد مشروع محدد")
        self.whisper_model_label = QLabel("")

        self.language_combo = QComboBox()
        for code, label in transcription.LANGUAGES.items():
            self.language_combo.addItem(label, code)

        self.transcribe_btn = QPushButton("بدء التفريغ الصوتي")
        self.transcribe_btn.clicked.connect(self.start_transcription)
        self.transcribe_cancel_btn = QPushButton("إلغاء")
        self.transcribe_cancel_btn.setEnabled(False)
        self.transcribe_cancel_btn.clicked.connect(lambda: self._cancel_worker())
        self.transcribe_progress = QProgressBar()
        self.transcribe_progress.setRange(0, 100)

        self.export_srt_btn = QPushButton("تصدير SRT")
        self.export_srt_btn.clicked.connect(self._export_srt)

        self.transcript_view = QPlainTextEdit()
        self.transcript_view.setReadOnly(True)

        layout.addWidget(self.project_info_label)
        layout.addWidget(self.whisper_model_label)
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("لغة الفيديو:"))
        lang_row.addWidget(self.language_combo)
        layout.addLayout(lang_row)
        row = QHBoxLayout()
        row.addWidget(self.transcribe_btn)
        row.addWidget(self.transcribe_cancel_btn)
        row.addWidget(self.transcribe_progress)
        row.addWidget(self.export_srt_btn)
        layout.addLayout(row)
        layout.addWidget(QLabel("النص المفرغ:"))
        layout.addWidget(self.transcript_view, 1)
        return w

    def _build_analysis_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        top_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        for key, label in config.ANALYSIS_MODES.items():
            self.mode_combo.addItem(label, key)
        self.analyze_btn = QPushButton("تحليل بالذكاء الاصطناعي")
        self.analyze_btn.clicked.connect(self.start_analysis)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 0)
        self.analysis_progress.setVisible(False)
        top_row.addWidget(QLabel("نمط التحليل:"))
        top_row.addWidget(self.mode_combo)
        top_row.addWidget(self.analyze_btn)
        top_row.addWidget(self.analysis_progress)
        layout.addLayout(top_row)

        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(
            ["تصدير؟", "اسم الموضوع", "النص", "البداية", "النهاية"]
        )
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.results_table, 1)
        return w

    def _build_export_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        row = QHBoxLayout()
        self.template_combo = QComboBox()
        self.template_combo.addItem("بدون قالب", None)
        row.addWidget(QLabel("القالب:"))
        row.addWidget(self.template_combo)

        self.output_dir_edit = QPushButton("اختيار مجلد الإخراج")
        self.output_dir_edit.clicked.connect(self._pick_output_dir)
        self._export_dir = db.get_setting("output_dir", "")
        row.addWidget(self.output_dir_edit)
        layout.addLayout(row)

        self.output_dir_label = QLabel(self._export_dir or "(لم يتم اختيار مجلد بعد)")
        layout.addWidget(self.output_dir_label)

        export_row = QHBoxLayout()
        self.export_btn = QPushButton("تصدير المقاطع المحددة")
        self.export_btn.clicked.connect(self.start_export)
        self.export_cancel_btn = QPushButton("إلغاء")
        self.export_cancel_btn.setEnabled(False)
        self.export_cancel_btn.clicked.connect(lambda: self._cancel_worker())
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        export_row.addWidget(self.export_btn)
        export_row.addWidget(self.export_cancel_btn)
        export_row.addWidget(self.export_progress)
        layout.addLayout(export_row)

        self.export_log = QPlainTextEdit()
        self.export_log.setReadOnly(True)
        layout.addWidget(self.export_log, 1)
        return w

    # ---------------- projects ----------------

    def refresh_project_list(self):
        self.project_list.blockSignals(True)
        self.project_list.clear()
        for p in db.list_projects():
            item = QListWidgetItem(f"{p.name} [{p.status}]")
            item.setData(Qt.UserRole, p.id)
            self.project_list.addItem(item)
        self.project_list.blockSignals(False)
        self._reload_templates_combo()
        if self.project_list.count():
            self.project_list.setCurrentRow(0)

    def _reload_templates_combo(self):
        self.template_combo.clear()
        self.template_combo.addItem("بدون قالب", None)
        for t in db.list_templates():
            self.template_combo.addItem(t.name, t.id)

    def on_project_selected(self, row):
        if row < 0:
            self.current_project = None
            return
        project_id = self.project_list.item(row).data(Qt.UserRole)
        self.current_project = db.get_project(project_id)
        self.current_segments = transcription.segments_from_json(
            self.current_project.transcript_json
        )
        self.current_topics = db.list_topics(project_id)
        self._refresh_transcribe_tab()
        self._refresh_results_table()

    def _refresh_transcribe_tab(self):
        p = self.current_project
        if not p:
            return
        self.project_info_label.setText(
            f"المشروع: {p.name} | المصدر: {p.source_type} | الحالة: {p.status}"
        )
        self.whisper_model_label.setText(f"نموذج Whisper: {p.whisper_model}")
        self.transcript_view.setPlainText(transcription.transcript_as_text(self.current_segments))

    def on_new_project(self):
        dlg = NewProjectDialog(self)
        if not dlg.exec():
            return
        data = dlg.result_data
        project = Project(
            id=None, name=data["name"], source_type=data["source_type"],
            source_url=data["source_value"], video_path="",
            whisper_model=data["whisper_model"], status="importing",
        )
        project.id = db.create_project(project)
        dest_dir = os.path.join(config.PROJECTS_DIR, str(project.id))

        self._set_busy(True, "جارٍ استيراد/تحميل الفيديو...")
        self._worker = WorkerThread(
            video_sources.resolve_video, project.source_type, project.source_url, dest_dir
        )
        self._worker.finished_ok.connect(lambda path: self._on_video_imported(project, path))
        self._worker.failed.connect(lambda msg: self._on_import_failed(project, msg))
        self._worker.start()

    def _on_video_imported(self, project: Project, video_path: str):
        project.video_path = video_path
        project.status = "imported"
        db.update_project(project)
        self._set_busy(False)
        self.refresh_project_list()
        QMessageBox.information(self, "تم", "تم استيراد الفيديو بنجاح")

    def _on_import_failed(self, project: Project, msg: str):
        self._set_busy(False)
        db.delete_project(project.id)
        QMessageBox.critical(self, "خطأ", f"فشل استيراد الفيديو:\n{msg}")
        self.refresh_project_list()

    def on_delete_project(self):
        if not self.current_project:
            return
        if QMessageBox.question(
            self, "تأكيد", f"حذف المشروع '{self.current_project.name}'؟"
        ) != QMessageBox.Yes:
            return
        db.delete_project(self.current_project.id)
        self.current_project = None
        self.refresh_project_list()

    # ---------------- transcription ----------------

    def start_transcription(self):
        if not self.current_project or not self.current_project.video_path:
            QMessageBox.warning(self, "تنبيه", "اختر مشروعًا يحتوي على فيديو أولاً")
            return
        self._set_busy(True, "جارٍ التفريغ الصوتي...")
        self.transcribe_progress.setValue(0)
        device = db.get_setting("whisper_device", "auto")
        compute_type = db.get_setting("whisper_compute_type", "default")
        language = self.language_combo.currentData()
        self._worker = WorkerThread(
            transcription.transcribe,
            self.current_project.video_path,
            self.current_project.whisper_model,
            device=device,
            compute_type=compute_type,
            language=language,
            report_progress=True,
            report_status=True,
            cancellable=True,
        )
        self._worker.progress.connect(lambda v: self.transcribe_progress.setValue(int(v * 100)))
        self._worker.status.connect(lambda msg: self.statusBar().showMessage(msg))
        self._worker.finished_ok.connect(self._on_transcription_done)
        self._worker.failed.connect(self._on_worker_error)
        self._worker.start()

    def _on_transcription_done(self, segments):
        self.current_segments = segments
        self.current_project.transcript_json = transcription.segments_to_json(segments)
        self.current_project.status = "transcribed"
        db.update_project(self.current_project)
        self._set_busy(False)
        self._refresh_transcribe_tab()
        self.refresh_project_list()
        QMessageBox.information(self, "تم", "اكتمل التفريغ الصوتي")

    def _export_srt(self):
        if not self.current_segments:
            QMessageBox.warning(self, "تنبيه", "لا يوجد نص مفرغ بعد")
            return
        default_name = f"{self.current_project.name}.srt" if self.current_project else "transcript.srt"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ ملف SRT", default_name, "SubRip (*.srt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(transcription.segments_to_srt(self.current_segments))
        QMessageBox.information(self, "تم", "تم حفظ ملف SRT بنجاح")

    # ---------------- analysis ----------------

    def start_analysis(self):
        if not self.current_segments:
            QMessageBox.warning(self, "تنبيه", "قم بالتفريغ الصوتي أولاً")
            return
        api_key = db.get_setting("api_key", "")
        provider_name = db.get_setting("ai_provider", "gemini")
        model_name = db.get_setting("ai_model", "")
        if not api_key:
            QMessageBox.warning(self, "تنبيه", "أدخل مفتاح API من الإعدادات أولاً")
            return
        provider = ai_providers.get_provider(provider_name, api_key, model_name)
        mode = self.mode_combo.currentData()

        self._set_busy(True, "جارٍ التحليل بالذكاء الاصطناعي...")
        self.analysis_progress.setVisible(True)
        self._worker = WorkerThread(
            analysis.analyze, provider, mode, self.current_segments, self.current_project.id
        )
        self._worker.finished_ok.connect(self._on_analysis_done)
        self._worker.failed.connect(self._on_worker_error)
        self._worker.start()

    def _on_analysis_done(self, topics):
        self.current_topics = topics
        db.replace_topics(self.current_project.id, topics)
        self.current_topics = db.list_topics(self.current_project.id)
        self.current_project.status = "analyzed"
        db.update_project(self.current_project)
        self._set_busy(False)
        self.analysis_progress.setVisible(False)
        self._refresh_results_table()
        self.refresh_project_list()

    def _refresh_results_table(self):
        self.results_table.setRowCount(0)
        for topic in self.current_topics:
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            checkbox = QCheckBox()
            checkbox.setChecked(topic.selected)
            checkbox.stateChanged.connect(
                lambda state, t=topic: self._on_topic_toggle(t, state)
            )
            self.results_table.setCellWidget(row, 0, checkbox)
            self.results_table.setItem(row, 1, QTableWidgetItem(topic.name))
            self.results_table.setItem(row, 2, QTableWidgetItem(topic.text))
            self.results_table.setItem(
                row, 3, QTableWidgetItem(transcription.format_timecode(topic.start))
            )
            self.results_table.setItem(
                row, 4, QTableWidgetItem(transcription.format_timecode(topic.end))
            )

    def _on_topic_toggle(self, topic: Topic, state):
        topic.selected = bool(state)
        if topic.id is not None:
            db.set_topic_selected(topic.id, topic.selected)

    # ---------------- export ----------------

    def _pick_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "اختر مجلد الإخراج", self._export_dir)
        if d:
            self._export_dir = d
            self.output_dir_label.setText(d)

    def start_export(self):
        if not self.current_project:
            return
        selected = [t for t in self.current_topics if t.selected]
        if not selected:
            QMessageBox.warning(self, "تنبيه", "لم يتم تحديد أي مقاطع للتصدير")
            return
        out_dir = self._export_dir or os.path.join(
            config.PROJECTS_DIR, str(self.current_project.id), "exports"
        )
        template_id = self.template_combo.currentData()
        template = db.get_template(template_id) if template_id else None

        self._set_busy(True, "جارٍ التصدير...")
        self.export_progress.setValue(0)
        self.export_log.clear()
        self._worker = WorkerThread(
            exporter.export_topics, self.current_project.video_path, selected, out_dir, template,
            report_progress=True, cancellable=True,
        )
        self._worker.progress.connect(lambda v: self.export_progress.setValue(int(v * 100)))
        self._worker.finished_ok.connect(self._on_export_done)
        self._worker.failed.connect(self._on_worker_error)
        self._worker.start()

    def _on_export_done(self, out_paths):
        self._set_busy(False)
        self.current_project.status = "exported"
        db.update_project(self.current_project)
        self.export_log.setPlainText("\n".join(out_paths))
        self.refresh_project_list()
        QMessageBox.information(self, "تم", f"تم تصدير {len(out_paths)} مقطع بنجاح")
        self._open_folder(os.path.dirname(out_paths[0]) if out_paths else "")

    def _open_folder(self, path):
        if not path or not os.path.isdir(path):
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])

    # ---------------- settings / templates ----------------

    def on_open_settings(self):
        SettingsDialog(self).exec()

    def on_open_templates(self):
        TemplatesManagerDialog(self).exec()
        self._reload_templates_combo()

    # ---------------- helpers ----------------

    def _set_busy(self, busy: bool, message: str = ""):
        for btn in (self.transcribe_btn, self.analyze_btn, self.export_btn):
            btn.setEnabled(not busy)
        for btn in (self.transcribe_cancel_btn, self.export_cancel_btn):
            btn.setEnabled(busy)
        if message:
            self.statusBar().showMessage(message)
        else:
            self.statusBar().clearMessage()

    def _cancel_worker(self):
        if self._worker is not None:
            self._worker.cancel()
            self.statusBar().showMessage("جارٍ الإلغاء...")

    def _on_worker_error(self, msg: str):
        self._set_busy(False)
        self.analysis_progress.setVisible(False)
        if msg == config.CANCELLED_MESSAGE:
            self.statusBar().showMessage("تم إلغاء العملية")
            return
        QMessageBox.critical(self, "خطأ", msg)
