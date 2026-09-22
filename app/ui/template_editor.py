"""Template editor: place the video rect and text boxes over a template image."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QColor, QBrush, QPen, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsTextItem, QPushButton, QLabel, QLineEdit,
    QSpinBox, QFormLayout, QWidget, QListWidget, QListWidgetItem,
    QColorDialog, QFileDialog, QMessageBox, QGroupBox
)

from .. import db
from ..models import Template, TextBox

HANDLE_SIZE = 10


class ResizableRectItem(QGraphicsRectItem):
    """A movable rectangle with a drag handle at the bottom-right corner."""

    def __init__(self, rect: QRectF):
        super().__init__(rect)
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIsSelectable
        )
        self.setPen(QPen(QColor("#00c8ff"), 2))
        self.setBrush(QBrush(QColor(0, 200, 255, 40)))
        self._resizing = False

    def _handle_rect(self):
        r = self.rect()
        return QRectF(r.right() - HANDLE_SIZE, r.bottom() - HANDLE_SIZE, HANDLE_SIZE, HANDLE_SIZE)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.fillRect(self._handle_rect(), QColor("#00c8ff"))

    def mousePressEvent(self, event):
        if self._handle_rect().contains(event.pos()):
            self._resizing = True
            self._resize_origin = event.pos()
            self._orig_rect = self.rect()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            dx = event.pos().x() - self._resize_origin.x()
            dy = event.pos().y() - self._resize_origin.y()
            new_w = max(20, self._orig_rect.width() + dx)
            new_h = max(20, self._orig_rect.height() + dy)
            self.setRect(QRectF(self._orig_rect.x(), self._orig_rect.y(), new_w, new_h))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        super().mouseReleaseEvent(event)


class DraggableTextItem(QGraphicsTextItem):
    def __init__(self, text_box: TextBox):
        super().__init__(text_box.text)
        self.text_box = text_box
        self.setFlags(
            QGraphicsTextItem.ItemIsMovable | QGraphicsTextItem.ItemIsSelectable
        )
        self.setDefaultTextColor(QColor(text_box.font_color))
        self.setFont(QFont(text_box.font_family, text_box.font_size))
        self.setPos(text_box.x, text_box.y)

    def sync_to_model(self):
        self.text_box.x = int(self.pos().x())
        self.text_box.y = int(self.pos().y())


class TemplateEditorDialog(QDialog):
    def __init__(self, template: Template = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("محرر القوالب")
        self.resize(1000, 700)

        self.template = template
        self.text_items: list[DraggableTextItem] = []
        self.video_item: ResizableRectItem = None

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(self.view.renderHints())

        # --- side panel ---
        self.name_edit = QLineEdit(template.name if template else "قالب جديد")
        load_img_btn = QPushButton("اختيار صورة القالب")
        load_img_btn.clicked.connect(self._load_image)

        self.canvas_w_spin = QSpinBox(); self.canvas_w_spin.setRange(64, 8000)
        self.canvas_h_spin = QSpinBox(); self.canvas_h_spin.setRange(64, 8000)

        video_group = QGroupBox("موضع الفيديو")
        vg_form = QFormLayout(video_group)
        self.vx = QSpinBox(); self.vx.setRange(0, 8000)
        self.vy = QSpinBox(); self.vy.setRange(0, 8000)
        self.vw = QSpinBox(); self.vw.setRange(10, 8000)
        self.vh = QSpinBox(); self.vh.setRange(10, 8000)
        apply_video_btn = QPushButton("تطبيق")
        apply_video_btn.clicked.connect(self._apply_video_rect_from_spins)
        vg_form.addRow("X:", self.vx)
        vg_form.addRow("Y:", self.vy)
        vg_form.addRow("العرض:", self.vw)
        vg_form.addRow("الارتفاع:", self.vh)
        vg_form.addRow(apply_video_btn)

        text_group = QGroupBox("النصوص")
        tg_layout = QVBoxLayout(text_group)
        self.text_list = QListWidget()
        self.text_list.currentRowChanged.connect(self._on_text_selected)
        add_text_btn = QPushButton("+ إضافة نص")
        add_text_btn.clicked.connect(self._add_text)
        remove_text_btn = QPushButton("حذف النص المحدد")
        remove_text_btn.clicked.connect(self._remove_text)

        self.text_content_edit = QLineEdit()
        self.text_content_edit.textChanged.connect(self._update_selected_text_content)
        self.text_size_spin = QSpinBox(); self.text_size_spin.setRange(6, 300)
        self.text_size_spin.valueChanged.connect(self._update_selected_text_font)
        color_btn = QPushButton("اختيار اللون")
        color_btn.clicked.connect(self._pick_text_color)

        tg_layout.addWidget(self.text_list)
        tg_layout.addWidget(add_text_btn)
        tg_layout.addWidget(remove_text_btn)
        tg_layout.addWidget(QLabel("النص:"))
        tg_layout.addWidget(self.text_content_edit)
        tg_layout.addWidget(QLabel("حجم الخط:"))
        tg_layout.addWidget(self.text_size_spin)
        tg_layout.addWidget(color_btn)

        save_btn = QPushButton("حفظ القالب")
        save_btn.clicked.connect(self._save)

        side = QWidget()
        side_l = QVBoxLayout(side)
        side_l.addWidget(QLabel("اسم القالب:"))
        side_l.addWidget(self.name_edit)
        side_l.addWidget(load_img_btn)
        side_l.addWidget(video_group)
        side_l.addWidget(text_group)
        side_l.addStretch()
        side_l.addWidget(save_btn)
        side.setFixedWidth(280)

        root = QHBoxLayout(self)
        root.addWidget(self.view, 1)
        root.addWidget(side)

        if template:
            self._load_template(template)

    # ---- loading ----

    def _load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر صورة القالب", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not path:
            return
        pixmap = QPixmap(path)
        self.image_path = path
        self.scene.clear()
        self.text_items = []
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self.canvas_w_spin.setValue(pixmap.width())
        self.canvas_h_spin.setValue(pixmap.height())
        w, h = pixmap.width() // 2, pixmap.height() // 2
        x, y = pixmap.width() // 4, pixmap.height() // 4
        self.video_item = ResizableRectItem(QRectF(0, 0, w, h))
        self.video_item.setPos(x, y)
        self.scene.addItem(self.video_item)
        self._sync_video_spins_from_item()

    def _load_template(self, t: Template):
        self.image_path = t.image_path
        pixmap = QPixmap(t.image_path)
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(0, 0, t.canvas_w, t.canvas_h)
        self.canvas_w_spin.setValue(t.canvas_w)
        self.canvas_h_spin.setValue(t.canvas_h)
        self.video_item = ResizableRectItem(QRectF(0, 0, t.video_w, t.video_h))
        self.video_item.setPos(t.video_x, t.video_y)
        self.scene.addItem(self.video_item)
        self._sync_video_spins_from_item()
        for tb in t.text_boxes:
            item = DraggableTextItem(tb)
            self.scene.addItem(item)
            self.text_items.append(item)
            self.text_list.addItem(QListWidgetItem(tb.text or "(نص)"))

    # ---- video rect ----

    def _sync_video_spins_from_item(self):
        if not self.video_item:
            return
        r = self.video_item.rect()
        self.vx.setValue(int(self.video_item.pos().x()))
        self.vy.setValue(int(self.video_item.pos().y()))
        self.vw.setValue(int(r.width()))
        self.vh.setValue(int(r.height()))

    def _apply_video_rect_from_spins(self):
        if not self.video_item:
            return
        self.video_item.setPos(self.vx.value(), self.vy.value())
        self.video_item.setRect(QRectF(0, 0, self.vw.value(), self.vh.value()))

    # ---- text boxes ----

    def _add_text(self):
        tb = TextBox(text="نص جديد", x=20, y=20)
        item = DraggableTextItem(tb)
        self.scene.addItem(item)
        self.text_items.append(item)
        self.text_list.addItem(QListWidgetItem(tb.text))
        self.text_list.setCurrentRow(len(self.text_items) - 1)

    def _remove_text(self):
        row = self.text_list.currentRow()
        if row < 0:
            return
        item = self.text_items.pop(row)
        self.scene.removeItem(item)
        self.text_list.takeItem(row)

    def _current_text_item(self):
        row = self.text_list.currentRow()
        if 0 <= row < len(self.text_items):
            return self.text_items[row]
        return None

    def _on_text_selected(self, row):
        item = self._current_text_item()
        if not item:
            return
        self.text_content_edit.blockSignals(True)
        self.text_content_edit.setText(item.text_box.text)
        self.text_content_edit.blockSignals(False)
        self.text_size_spin.blockSignals(True)
        self.text_size_spin.setValue(item.text_box.font_size)
        self.text_size_spin.blockSignals(False)

    def _update_selected_text_content(self, text):
        item = self._current_text_item()
        if not item:
            return
        item.text_box.text = text
        item.setPlainText(text)
        self.text_list.currentItem().setText(text or "(نص)")

    def _update_selected_text_font(self, size):
        item = self._current_text_item()
        if not item:
            return
        item.text_box.font_size = size
        item.setFont(QFont(item.text_box.font_family, size))

    def _pick_text_color(self):
        item = self._current_text_item()
        if not item:
            return
        color = QColorDialog.getColor(QColor(item.text_box.font_color), self)
        if color.isValid():
            item.text_box.font_color = color.name()
            item.setDefaultTextColor(color)

    # ---- save ----

    def _save(self):
        if not getattr(self, "image_path", None):
            QMessageBox.warning(self, "تنبيه", "اختر صورة القالب أولاً")
            return
        for item in self.text_items:
            item.sync_to_model()
        t = Template(
            id=self.template.id if self.template else None,
            name=self.name_edit.text().strip() or "قالب",
            image_path=self.image_path,
            canvas_w=self.canvas_w_spin.value(),
            canvas_h=self.canvas_h_spin.value(),
            video_x=self.vx.value(), video_y=self.vy.value(),
            video_w=self.vw.value(), video_h=self.vh.value(),
            text_boxes=[it.text_box for it in self.text_items],
        )
        # keep spinboxes in sync with any manual drag/resize on the video rect
        if self.video_item:
            t.video_x = int(self.video_item.pos().x())
            t.video_y = int(self.video_item.pos().y())
            t.video_w = int(self.video_item.rect().width())
            t.video_h = int(self.video_item.rect().height())
        db.save_template(t)
        self.accept()


class TemplatesManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة القوالب")
        self.resize(400, 400)

        self.list_widget = QListWidget()
        self._reload()

        new_btn = QPushButton("قالب جديد")
        new_btn.clicked.connect(self._new_template)
        edit_btn = QPushButton("تعديل")
        edit_btn.clicked.connect(self._edit_template)
        delete_btn = QPushButton("حذف")
        delete_btn.clicked.connect(self._delete_template)

        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(delete_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addLayout(btn_row)

    def _reload(self):
        self.list_widget.clear()
        self._templates = db.list_templates()
        for t in self._templates:
            item = QListWidgetItem(t.name)
            item.setData(Qt.UserRole, t.id)
            self.list_widget.addItem(item)

    def _selected_template(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._templates):
            return self._templates[row]
        return None

    def _new_template(self):
        dlg = TemplateEditorDialog(parent=self)
        if dlg.exec():
            self._reload()

    def _edit_template(self):
        t = self._selected_template()
        if not t:
            return
        dlg = TemplateEditorDialog(template=t, parent=self)
        if dlg.exec():
            self._reload()

    def _delete_template(self):
        t = self._selected_template()
        if not t:
            return
        if QMessageBox.question(self, "تأكيد", f"حذف القالب '{t.name}'؟") == QMessageBox.Yes:
            db.delete_template(t.id)
            self._reload()
